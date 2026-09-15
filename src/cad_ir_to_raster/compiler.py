"""
compiler.py - Core IR-to-Raster compilation engine for cad-ir-to-raster.

Pipeline (all in-memory, zero mandatory disk I/O):
  LAVINCI_CAD_IR_V3 -> cad_ir_to_svg_string() -> SVG bytes
  -> PyMuPDF.open(stream=svg) -> Pixmap at target DPI
  -> encode to PNG / JPEG / WebP bytes
  -> write to file OR return raw bytes (headless API / Lambda mode)
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

# Dependency: cad-ir-to-svg
try:
    from cad_ir_to_svg import compile_ir_to_svg_string, PRESETS as SVG_PRESETS
    from cad_ir_to_svg.config import DEFAULT_PRESET as SVG_DEFAULT_PRESET
except ImportError as e:
    raise ImportError(
        "cad-ir-to-svg is required by cad-ir-to-raster. "
        "Install it via: pip install -e ../cad-ir-to-svg"
    ) from e

# Dependency: PyMuPDF
try:
    import pymupdf
except ImportError as e:
    raise ImportError(
        "PyMuPDF is required. Install: pip install pymupdf>=1.20.0"
    ) from e

# Dependency: Pillow (for WebP)
try:
    from PIL import Image as PilImage
    _PILLOW_AVAILABLE = True
except ImportError:
    _PILLOW_AVAILABLE = False

from .config import DEFAULT_PRESET, PRESETS, RasterPreset
from .telemetry import RasterReport


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load_ir_dict(ir_source: Union[str, Path, Dict[str, Any], Any]) -> Dict[str, Any]:
    """Converts any supported IR source into a plain Python dict."""
    if isinstance(ir_source, dict):
        return ir_source
    if hasattr(ir_source, "model_dump"):
        return ir_source.model_dump()
    if hasattr(ir_source, "dict") and callable(ir_source.dict):
        return ir_source.dict()
    if isinstance(ir_source, (str, Path)):
        s = str(ir_source).strip()
        if s.startswith("{"):
            try:
                return json.loads(s)
            except Exception:
                pass
        p = Path(ir_source)
        if p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    raise ValueError(
        f"Cannot parse CAD IR payload from source type {type(ir_source)}. "
        "Expected: dict, Path to JSON file, or raw JSON string."
    )


def _resolve_preset(preset: Optional[Union[RasterPreset, str]]) -> RasterPreset:
    """Resolves preset name or instance. Defaults to DEFAULT_PRESET."""
    if preset is None:
        return DEFAULT_PRESET
    if isinstance(preset, RasterPreset):
        return preset
    if isinstance(preset, str):
        if preset not in PRESETS:
            raise ValueError(
                f"Unknown preset: '{preset}'. Available: {list(PRESETS.keys())}"
            )
        return PRESETS[preset]
    raise TypeError(f"preset must be RasterPreset or str, got {type(preset)}")


def _resolve_svg_preset_name(raster_preset: RasterPreset) -> str:
    """Maps a RasterPreset to the best matching SvgPreset name."""
    color_mode = raster_preset.color_mode
    bg = raster_preset.background_color.upper().strip()
    if color_mode == "monochrome":
        return "architectural-monochrome"
    if color_mode == "aci" or bg in ("#1E1E1E", "#000000", "#1A1A1A"):
        return "cad-dark-modelspace"
    return "web-interactive-light"


def _encode_pixmap(pix: Any, fmt: str, preset: RasterPreset) -> bytes:
    """Encodes a PyMuPDF Pixmap to the requested format as bytes."""
    fmt = fmt.lower()
    if fmt == "png":
        return pix.tobytes("png")
    if fmt in ("jpeg", "jpg"):
        if pix.alpha:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        return pix.tobytes("jpeg")
    if fmt == "webp":
        if not _PILLOW_AVAILABLE:
            raise ImportError(
                "Pillow is required for WebP encoding: pip install Pillow>=9.0.0"
            )
        png_bytes = pix.tobytes("png")
        img = PilImage.open(io.BytesIO(png_bytes)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=preset.webp_quality, method=4)
        return buf.getvalue()
    raise ValueError(f"Unsupported format: '{fmt}'. Use png, jpeg, or webp.")


def _apply_max_dimension(pix: Any, max_dim: Optional[int]) -> Any:
    """Proportionally downscales a Pixmap if it exceeds max_dim on any axis."""
    if max_dim is None or max_dim <= 0:
        return pix
    w, h = pix.width, pix.height
    if w <= max_dim and h <= max_dim:
        return pix
    if not _PILLOW_AVAILABLE:
        return pix  # skip silently
    scale = max_dim / max(w, h)
    new_w = max(1, round(w * scale))
    new_h = max(1, round(h * scale))
    png_bytes = pix.tobytes("png")
    img = PilImage.open(io.BytesIO(png_bytes)).convert("RGB").resize(
        (new_w, new_h), PilImage.LANCZOS
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    doc = pymupdf.open(stream=buf.getvalue(), filetype="png")
    return doc[0].get_pixmap()


def _count_entities(ir: Dict[str, Any]) -> int:
    """Counts total geometric + annotation entities for telemetry."""
    total = 0
    geom = ir.get("geometry_primitives")
    if isinstance(geom, dict):
        prims = geom.get("primitives", {})
        if isinstance(prims, dict):
            for k in ("lines", "arcs", "circles", "polylines"):
                v = prims.get(k)
                if isinstance(v, list):
                    total += len(v)
    for k in ("components", "annotations", "dimensions"):
        v = ir.get(k)
        if isinstance(v, list):
            total += len(v)
    return total


# ── Public API ────────────────────────────────────────────────────────────────

def compile_ir_to_raster(
    ir_source: Union[str, Path, Dict[str, Any], Any],
    output_path: Optional[Union[str, Path]] = None,
    preset: Optional[Union[RasterPreset, str]] = None,
    format: Optional[str] = None,
    dpi: Optional[int] = None,
    return_report: bool = False,
) -> Union[Path, bytes, Tuple[Union[Path, bytes], RasterReport]]:
    """
    Compiles a LAVINCI_CAD_IR_V3 payload into a high-fidelity raster image.

    Parameters
    ----------
    ir_source : str | Path | dict | Pydantic model
        The CAD IR: filepath to JSON, raw JSON string, parsed dict, or Pydantic model.
    output_path : str | Path | None
        If provided, writes the raster image to this file path.
        If None, returns raw image bytes (headless API / Lambda mode).
    preset : RasterPreset | str | None
        Preset instance or preset name. Defaults to "web-preview" (PNG, 150 DPI).
    format : str | None
        Override format ("png", "jpeg", "webp"). Overrides preset format if set.
    dpi : int | None
        Override DPI. Overrides preset DPI if set.
    return_report : bool
        If True, returns (output, RasterReport) tuple. Default: False.

    Returns
    -------
    Path | bytes
        File Path (if output_path given) or raw image bytes.
    Tuple[Path | bytes, RasterReport]
        With report when return_report=True.
    """
    t0 = time.perf_counter()
    report = RasterReport()

    # Resolve active preset (with per-call overrides)
    active_preset = _resolve_preset(preset)
    if format is not None or dpi is not None:
        active_preset = RasterPreset(
            name=active_preset.name,
            format=format if format is not None else active_preset.format,
            dpi=dpi if dpi is not None else active_preset.dpi,
            background_color=active_preset.background_color,
            color_mode=active_preset.color_mode,
            padding_percent=active_preset.padding_percent,
            max_dimension=active_preset.max_dimension,
            jpeg_quality=active_preset.jpeg_quality,
            webp_quality=active_preset.webp_quality,
        )

    report.preset_name = active_preset.name
    report.format = active_preset.normalized_format
    report.dpi = active_preset.dpi

    # Load IR
    ir = _load_ir_dict(ir_source)
    report.total_entities_read = _count_entities(ir)

    ext = ir.get("extents")
    if isinstance(ext, dict):
        report.cad_bbox_extents = {
            "min_x": ext.get("min", [0, 0])[0],
            "min_y": ext.get("min", [0, 0])[1],
            "max_x": ext.get("max", [0, 0])[0],
            "max_y": ext.get("max", [0, 0])[1],
            "width": ext.get("width", 0.0),
            "height": ext.get("height", 0.0),
        }

    # Stage 1: Compile IR to in-memory SVG (via cad-ir-to-svg engine)
    svg_preset_name = _resolve_svg_preset_name(active_preset)
    svg_preset = SVG_PRESETS.get(svg_preset_name, SVG_DEFAULT_PRESET)
    svg_str, svg_report = compile_ir_to_svg_string(ir, preset=svg_preset)
    report.total_entities_rendered = svg_report.total_entities_rendered
    report.total_entities_dropped = svg_report.total_entities_dropped

    # Stage 2: Rasterize SVG -> PyMuPDF Pixmap at target DPI
    mupdf_doc = pymupdf.open(stream=svg_str.encode("utf-8"), filetype="svg")
    pix = mupdf_doc[0].get_pixmap(dpi=active_preset.dpi)
    mupdf_doc.close()

    # Stage 3: Apply max_dimension cap
    pix = _apply_max_dimension(pix, active_preset.max_dimension)

    # Stage 4: Encode to target format bytes
    image_bytes = _encode_pixmap(pix, active_preset.normalized_format, active_preset)

    # Populate report
    t1 = time.perf_counter()
    report.pixel_width = pix.width
    report.pixel_height = pix.height
    report.file_size_bytes = len(image_bytes)
    report.render_time_ms = (t1 - t0) * 1000.0
    report.success = True

    # Return
    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(image_bytes)
        report.output_target = str(out)
        result: Union[Path, bytes] = out
    else:
        report.output_target = "<in-memory>"
        result = image_bytes

    return (result, report) if return_report else result


def get_raster_dimensions(
    ir_source: Union[str, Path, Dict[str, Any], Any],
    preset: Optional[Union[RasterPreset, str]] = None,
    dpi: Optional[int] = None,
) -> Tuple[int, int]:
    """
    Returns (pixel_width, pixel_height) that would be generated by compile_ir_to_raster
    without performing the full encoding step. Useful for pre-flight API metadata.
    """
    active_preset = _resolve_preset(preset)
    if dpi is not None:
        active_preset = RasterPreset(
            name=active_preset.name,
            format=active_preset.format,
            dpi=dpi,
            background_color=active_preset.background_color,
            color_mode=active_preset.color_mode,
            padding_percent=active_preset.padding_percent,
            max_dimension=active_preset.max_dimension,
        )
    ir = _load_ir_dict(ir_source)
    svg_preset_name = _resolve_svg_preset_name(active_preset)
    svg_preset = SVG_PRESETS.get(svg_preset_name, SVG_DEFAULT_PRESET)
    svg_str, _ = compile_ir_to_svg_string(ir, preset=svg_preset)
    mupdf_doc = pymupdf.open(stream=svg_str.encode("utf-8"), filetype="svg")
    pix = mupdf_doc[0].get_pixmap(dpi=active_preset.dpi)
    mupdf_doc.close()
    w, h = pix.width, pix.height
    if active_preset.max_dimension:
        scale = active_preset.max_dimension / max(w, h)
        if scale < 1.0:
            w = max(1, round(w * scale))
            h = max(1, round(h * scale))
    return w, h
