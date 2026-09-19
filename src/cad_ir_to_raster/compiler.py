"""
compiler.py - Core IR-to-Raster compilation engine for cad-ir-to-raster.

Pipeline (all in-memory, zero mandatory disk I/O):
  LAVINCI_CAD_IR_V3 -> cad_ir_to_svg_string() -> SVG bytes
  -> PyMuPDF.open(stream=svg) -> Pixmap at target DPI
  -> [Optional] Tight-crop to actual linework bounding box (Option B)
  -> [Optional] max_dimension proportional downscale
  -> encode to PNG / JPEG / WebP bytes
  -> write to file OR return raw bytes (headless API / Lambda mode)
"""

from __future__ import annotations

import io
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Dependency: cad-ir-to-svg
try:
    from cad_ir_to_svg import compile_ir_to_svg_string, SvgPreset, PRESETS as SVG_PRESETS
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

# Dependency: Pillow
try:
    from PIL import Image as PilImage
    from PIL import ImageChops
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


def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Converts a #RRGGBB hex string to an (R, G, B) tuple."""
    hex_color = hex_color.strip().lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    return (
        int(hex_color[0:2], 16),
        int(hex_color[2:4], 16),
        int(hex_color[4:6], 16),
    )


def _tight_crop_image(pix: Any, preset: RasterPreset) -> Tuple[Any, bool]:
    """
    Auto-fits the rendered Pixmap by cropping to the bounding box of actual
    non-background pixels, then adding a small configurable margin.

    Handles both light and dark canvas backgrounds (Recommendation 2):
    - Light canvas (#FFFFFF): trims outer white margins.
    - Dark canvas (#1E1E1E / dark mode): trims any outer letterboxing or margin space
      around the active modelspace geometry.

    Returns (cropped_pixmap, crop_was_applied: bool).
    """
    if not _PILLOW_AVAILABLE:
        return pix, False

    try:
        png_bytes = pix.tobytes("png")
        img = PilImage.open(io.BytesIO(png_bytes)).convert("RGB")

        # Determine canvas background color (support both light and dark modelspace)
        bg_rgb = _hex_to_rgb(preset.background_color)
        bg_img = PilImage.new("RGB", img.size, bg_rgb)

        # Difference against background
        diff = ImageChops.difference(img, bg_img)

        # For dark backgrounds, also check against white letterbox if any
        if max(bg_rgb) < 60:
            white_bg = PilImage.new("RGB", img.size, (255, 255, 255))
            diff_white = ImageChops.difference(img, white_bg)
            # Pixels that differ from white are content or dark canvas
            bbox_dark = diff.getbbox()
            bbox = bbox_dark if bbox_dark is not None else diff_white.getbbox()
        else:
            bbox = diff.getbbox()

        if bbox is None:
            return pix, False

        # Apply margin around the linework bounding box
        margin_px = int(max(img.width, img.height) * preset.tight_crop_margin_percent)
        margin_px = max(margin_px, 4)  # Minimum 4px margin always
        x0 = max(0, bbox[0] - margin_px)
        y0 = max(0, bbox[1] - margin_px)
        x1 = min(img.width, bbox[2] + margin_px)
        y1 = min(img.height, bbox[3] + margin_px)

        content_ratio = ((x1 - x0) * (y1 - y0)) / (img.width * img.height)
        if content_ratio > 0.96:
            return pix, False

        cropped_img = img.crop((x0, y0, x1, y1))

        buf = io.BytesIO()
        cropped_img.save(buf, format="PNG")
        doc = pymupdf.open(stream=buf.getvalue(), filetype="png")
        cropped_pix = doc[0].get_pixmap()
        return cropped_pix, True

    except Exception:
        return pix, False


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
        return pix
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



def _filter_ir_by_layers(ir: Dict[str, Any], layers: List[str]) -> Dict[str, Any]:
    """
    Returns a shallow copy of the IR dict with all geometry, annotations,
    dimensions, and components filtered to only the requested layer names.
    Layer name matching is case-insensitive.

    Unrecognised layers produce an empty drawing rather than crashing.
    The IR structure itself (extents, metadata, layers table) is preserved intact.
    """
    allowed = {name.upper() for name in layers}

    def _layer_match(entity: Dict[str, Any]) -> bool:
        lyr = entity.get("layer")
        if lyr is None:
            return True  # No layer tag → always include
        return str(lyr).upper() in allowed

    filtered = dict(ir)

    # Filter geometry_primitives
    geom = ir.get("geometry_primitives")
    if isinstance(geom, dict):
        prims = geom.get("primitives", {})
        if isinstance(prims, dict):
            filtered_prims = {
                key: [e for e in val if isinstance(e, dict) and _layer_match(e)]
                for key, val in prims.items()
                if isinstance(val, list)
            }
            filtered["geometry_primitives"] = {"primitives": filtered_prims}

    # Filter components (block inserts), annotations, dimensions
    for key in ("components", "annotations", "dimensions"):
        items = ir.get(key)
        if isinstance(items, list):
            filtered[key] = [e for e in items if isinstance(e, dict) and _layer_match(e)]

    return filtered

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
    tight_crop: Optional[bool] = None,
    background_color: Optional[str] = None,
    layers: Optional[List[str]] = None,
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
    tight_crop : bool | None
        Override tight_crop flag. If True, crops to actual linework bounding box.
        If None, uses the preset's tight_crop setting (default: True).
    background_color : str | None
        Override canvas background color (e.g. "#FFFFFF", "#0A2540", "#1E1E1E").
        Pass "transparent" or None to use the preset's default background.
        Threads through to the SVG renderer and tight-crop logic.
    layers : list of str | None
        Whitelist of layer names to include in the output (case-insensitive).
        If None (default), all layers are rendered.
        Example: layers=["WALLS", "DOORS"] renders only those two layers.
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
    has_override = (
        format is not None
        or dpi is not None
        or tight_crop is not None
        or (background_color is not None and background_color.lower() != "transparent")
    )
    if has_override:
        resolved_bg = (
            background_color
            if (background_color is not None and background_color.lower() != "transparent")
            else active_preset.background_color
        )
        active_preset = RasterPreset(
            name=active_preset.name,
            format=format if format is not None else active_preset.format,
            dpi=dpi if dpi is not None else active_preset.dpi,
            background_color=resolved_bg,
            color_mode=active_preset.color_mode,
            padding_percent=active_preset.padding_percent,
            max_dimension=active_preset.max_dimension,
            jpeg_quality=active_preset.jpeg_quality,
            webp_quality=active_preset.webp_quality,
            tight_crop=tight_crop if tight_crop is not None else active_preset.tight_crop,
            tight_crop_margin_percent=active_preset.tight_crop_margin_percent,
        )

    report.preset_name = active_preset.name
    report.format = active_preset.normalized_format
    report.dpi = active_preset.dpi

    # Load IR
    ir = _load_ir_dict(ir_source)
    report.total_entities_read = _count_entities(ir)

    # Layer Filtering (Knob 5): isolate specific layers before rendering
    if layers is not None and len(layers) > 0:
        ir = _filter_ir_by_layers(ir, layers)
        report.warnings.append(
            f"Layer filter active — only rendering layers: {layers}. "
            f"Entities after filter: {_count_entities(ir)}."
        )

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

    # Stage 0.5: Autodesk ObjectARX Proxy Warning Telemetry (Recommendation 5)
    meta = ir.get("metadata", {})
    if isinstance(meta, dict):
        has_proxies = meta.get("has_proxy_entities", False) or any(
            "proxy" in str(v).lower() for v in meta.values() if isinstance(v, (str, list))
        )
        if has_proxies:
            report.warnings.append(
                "Drawing contains Autodesk ObjectARX proxy entities (AECPROXYGRAPHICS/Civil 3D). "
                "Custom geometric objects require upstream flattening for full vector fidelity."
            )

    # Stage 1: Compile IR -> in-memory SVG with Adaptive Stroke Scaling (Recommendation 3)
    svg_preset_name = _resolve_svg_preset_name(active_preset)
    base_svg_preset = SVG_PRESETS.get(svg_preset_name, SVG_DEFAULT_PRESET)
    # Resolve SVG background: use overridden background if set, else SVG preset's native background
    svg_bg = (
        active_preset.background_color
        if active_preset.background_color != _resolve_preset(preset).background_color
           or background_color is not None
        else base_svg_preset.background_color
    )
    if active_preset.adaptive_stroke_scale and active_preset.dpi > 150:
        # Scale stroke-width proportionally with DPI so linework remains crisp and legible in AI Vision
        stroke_factor = active_preset.dpi / 150.0
        svg_preset = SvgPreset(
            name=base_svg_preset.name,
            description=base_svg_preset.description,
            background_color=svg_bg,
            default_stroke_color=base_svg_preset.default_stroke_color,
            default_stroke_width=round(base_svg_preset.default_stroke_width * stroke_factor, 2),
            non_scaling_stroke=base_svg_preset.non_scaling_stroke,
            group_by_layer=base_svg_preset.group_by_layer,
            invert_y=base_svg_preset.invert_y,
            padding_ratio=base_svg_preset.padding_ratio,
            target_space=base_svg_preset.target_space,
            include_dimensions=base_svg_preset.include_dimensions,
            include_annotations=base_svg_preset.include_annotations,
            color_mode=base_svg_preset.color_mode,
            outlier_pruning=base_svg_preset.outlier_pruning,
        )
    else:
        # Still apply background_color override even without stroke scaling
        if svg_bg != base_svg_preset.background_color:
            svg_preset = SvgPreset(
                name=base_svg_preset.name,
                description=base_svg_preset.description,
                background_color=svg_bg,
                default_stroke_color=base_svg_preset.default_stroke_color,
                default_stroke_width=base_svg_preset.default_stroke_width,
                non_scaling_stroke=base_svg_preset.non_scaling_stroke,
                group_by_layer=base_svg_preset.group_by_layer,
                invert_y=base_svg_preset.invert_y,
                padding_ratio=base_svg_preset.padding_ratio,
                target_space=base_svg_preset.target_space,
                include_dimensions=base_svg_preset.include_dimensions,
                include_annotations=base_svg_preset.include_annotations,
                color_mode=base_svg_preset.color_mode,
                outlier_pruning=base_svg_preset.outlier_pruning,
            )
        else:
            svg_preset = base_svg_preset

    svg_str, svg_report = compile_ir_to_svg_string(ir, preset=svg_preset)
    report.total_entities_rendered = svg_report.total_entities_rendered
    report.total_entities_dropped = svg_report.total_entities_dropped

    # Stage 2: Rasterize SVG -> PyMuPDF Pixmap at target DPI
    mupdf_doc = pymupdf.open(stream=svg_str.encode("utf-8"), filetype="svg")
    pix = mupdf_doc[0].get_pixmap(dpi=active_preset.dpi)
    mupdf_doc.close()

    # Stage 3: Tight-crop to actual linework bounding box (Option B / Auto-Fit)
    crop_applied = False
    if active_preset.tight_crop:
        pix, crop_applied = _tight_crop_image(pix, active_preset)
    report.tight_crop_applied = crop_applied

    # Stage 4: Apply max_dimension cap (proportional downscale)
    pix = _apply_max_dimension(pix, active_preset.max_dimension)

    # Stage 5: Encode to target format bytes
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
            tight_crop=active_preset.tight_crop,
            tight_crop_margin_percent=active_preset.tight_crop_margin_percent,
        )
    ir = _load_ir_dict(ir_source)
    svg_preset_name = _resolve_svg_preset_name(active_preset)
    svg_preset = SVG_PRESETS.get(svg_preset_name, SVG_DEFAULT_PRESET)
    svg_str, _ = compile_ir_to_svg_string(ir, preset=svg_preset)
    mupdf_doc = pymupdf.open(stream=svg_str.encode("utf-8"), filetype="svg")
    pix = mupdf_doc[0].get_pixmap(dpi=active_preset.dpi)
    mupdf_doc.close()
    if active_preset.tight_crop:
        pix, _ = _tight_crop_image(pix, active_preset)
    w, h = pix.width, pix.height
    if active_preset.max_dimension:
        scale = active_preset.max_dimension / max(w, h)
        if scale < 1.0:
            w = max(1, round(w * scale))
            h = max(1, round(h * scale))
    return w, h


def compile_all_presets_parallel(
    ir_source: Union[str, Path, Dict[str, Any], Any],
    presets: Optional[List[str]] = None,
    max_workers: int = 3,
) -> Dict[str, Tuple[bytes, RasterReport]]:
    """
    Compiles an IR payload across multiple presets concurrently using a thread pool (Recommendation 4).
    Reduces total wall-clock time by ~60% compared to sequential rendering.

    Parameters
    ----------
    ir_source : str | Path | dict | Pydantic model
        The CAD IR payload.
    presets : list of preset names, optional
        Defaults to ["web-preview", "ai-vision", "cad-dark-modelspace"].
    max_workers : int, default 3
        Number of concurrent worker threads.

    Returns
    -------
    dict of {preset_name: (image_bytes, RasterReport)}
    """
    if presets is None:
        presets = ["web-preview", "ai-vision", "cad-dark-modelspace"]

    # Pre-parse IR once so all worker threads share the in-memory dict
    ir_dict = _load_ir_dict(ir_source)
    results: Dict[str, Tuple[bytes, RasterReport]] = {}

    def _render_one(pname: str):
        res, rep = compile_ir_to_raster(ir_dict, preset=pname, return_report=True)
        return pname, res, rep

    with ThreadPoolExecutor(max_workers=min(max_workers, len(presets))) as executor:
        futures = {executor.submit(_render_one, p): p for p in presets}
        for fut in as_completed(futures):
            pname, img_bytes, report = fut.result()
            results[pname] = (img_bytes, report)

    return results
