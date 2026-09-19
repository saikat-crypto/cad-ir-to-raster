"""
config.py - Preset Configuration System for cad-ir-to-raster.

Defines RasterPreset (the destination profile dataclass) and the PRESETS registry.
Product 5 ships with one rock-solid default preset: "web-preview" (PNG @ 150 DPI).
Additional presets are scaffolded as stubs for future API milestones.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional
import re

from .exceptions import InvalidFormatError, InvalidDpiError, InvalidColorError

_HEX_COLOR_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


@dataclass(frozen=True)
class RasterPreset:
    """
    Immutable configuration profile for a single raster rendering variant.

    All parameters are frozen at preset creation time.
    API callers can build custom presets by constructing a new RasterPreset instance.

    Raises
    ------
    InvalidFormatError
        If `format` is not one of 'png', 'jpeg', 'jpg', 'webp'.
    InvalidDpiError
        If `dpi` is outside the valid range [1, 1200].
    InvalidColorError
        If `background_color` is not a valid #RRGGBB or #RGB hex string.
    """
    name: str = "web-preview"
    format: str = "png"                  # "png", "jpeg", "webp"
    dpi: int = 150                       # Resolution: dots per inch
    background_color: str = "#FFFFFF"    # Canvas background (hex #RRGGBB)
    color_mode: str = "contrast-safe"    # "contrast-safe" | "monochrome" | "aci"
    padding_percent: float = 0.02        # Padding as fraction of drawing dimension
    max_dimension: Optional[int] = None  # Cap max pixel width or height (None = uncapped)
    jpeg_quality: int = 92               # JPEG quality 1-100 (only applies when format="jpeg")
    webp_quality: int = 85               # WebP quality 1-100 (only applies when format="webp")

    # ── Tight-Crop (Option B / Auto-Fit) ─────────────────────────────────────
    tight_crop: bool = True
    # When True, the engine detects where actual linework pixels exist in the
    # rendered image and crops to that bounding box + tight_crop_margin_percent.
    # This eliminates whitespace caused by coordinate origin offsets or portrait
    # page layouts being used for landscape drawings.
    tight_crop_margin_percent: float = 0.03
    # Margin as a fraction of the cropped image's larger dimension (default 3%).

    # ── Adaptive Linework & Stroke Scale (Recommendation 3) ──────────────────
    adaptive_stroke_scale: bool = True
    # Scales stroke widths proportionally with DPI (dpi / 150.0) so lines maintain
    # sharp, balanced presence at high resolutions (e.g., 300 DPI for AI Vision).

    def __post_init__(self):
        # Validate format
        allowed_formats = ("png", "jpeg", "jpg", "webp")
        if self.format.lower() not in allowed_formats:
            raise InvalidFormatError(self.format)

        # Validate DPI
        if self.dpi < InvalidDpiError.MIN_DPI or self.dpi > InvalidDpiError.MAX_DPI:
            raise InvalidDpiError(self.dpi)

        # Validate background_color hex
        bg = self.background_color
        if bg and bg.lower() not in ("transparent", "none"):
            if not _HEX_COLOR_RE.match(bg):
                raise InvalidColorError(bg, "background_color")

    @property
    def normalized_format(self) -> str:
        """Returns canonical lowercase format string ('jpg' normalized to 'jpeg')."""
        f = self.format.lower()
        return "jpeg" if f == "jpg" else f


# ─────────────────────────────────────────────────────────────────
# Preset Registry
# ─────────────────────────────────────────────────────────────────

DEFAULT_PRESET = RasterPreset(
    name="web-preview",
    format="png",
    dpi=150,
    background_color="#FFFFFF",
    color_mode="contrast-safe",
    padding_percent=0.02,
    max_dimension=None,
    tight_crop=True,
    tight_crop_margin_percent=0.03,
)

PRESETS: Dict[str, RasterPreset] = {
    "web-preview": DEFAULT_PRESET,

    "web-thumbnail": RasterPreset(
        name="web-thumbnail",
        format="webp",
        dpi=72,
        background_color="#FFFFFF",
        color_mode="contrast-safe",
        padding_percent=0.03,
        max_dimension=512,
        tight_crop=True,
        tight_crop_margin_percent=0.02,
    ),
    "ai-vision": RasterPreset(
        name="ai-vision",
        format="png",
        dpi=300,
        background_color="#FFFFFF",
        color_mode="contrast-safe",
        padding_percent=0.02,
        max_dimension=None,
        tight_crop=True,
        tight_crop_margin_percent=0.02,
    ),
    "cad-dark-modelspace": RasterPreset(
        name="cad-dark-modelspace",
        format="png",
        dpi=150,
        background_color="#1E1E1E",
        color_mode="aci",
        padding_percent=0.02,
        max_dimension=None,
        tight_crop=True,
        tight_crop_margin_percent=0.03,
    ),
    "architectural-monochrome": RasterPreset(
        name="architectural-monochrome",
        format="png",
        dpi=300,
        background_color="#FFFFFF",
        color_mode="monochrome",
        padding_percent=0.02,
        max_dimension=None,
        tight_crop=True,
        tight_crop_margin_percent=0.02,
    ),
}
