"""
config.py — Preset Configuration System for cad-ir-to-raster.

Defines RasterPreset (the destination profile dataclass) and the PRESETS registry.
Product 5 ships with one rock-solid default preset: "web-preview" (PNG @ 150 DPI).
Additional presets are scaffolded as stubs for future API milestones.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass(frozen=True)
class RasterPreset:
    """
    Immutable configuration profile for a single raster rendering variant.

    All parameters are frozen at preset creation time.
    API callers can build custom presets by constructing a new RasterPreset instance.
    """
    name: str = "web-preview"
    format: str = "png"             # "png", "jpeg", "webp"
    dpi: int = 150                  # Resolution: dots per inch
    background_color: str = "#FFFFFF"  # Canvas background (hex)
    color_mode: str = "contrast-safe"  # "contrast-safe" | "monochrome" | "aci"
    padding_percent: float = 0.02   # Padding as fraction of drawing dimension
    max_dimension: Optional[int] = None  # Cap max pixel width or height (None = uncapped)
    jpeg_quality: int = 92          # JPEG quality 1-100 (only applies when format="jpeg")
    webp_quality: int = 85          # WebP quality 1-100 (only applies when format="webp")

    def __post_init__(self):
        # Validate format
        allowed_formats = ("png", "jpeg", "jpg", "webp")
        if self.format.lower() not in allowed_formats:
            raise ValueError(
                f"Unsupported raster format '{self.format}'. "
                f"Must be one of: {allowed_formats}"
            )
        if self.dpi < 1 or self.dpi > 1200:
            raise ValueError(f"DPI must be between 1 and 1200. Got: {self.dpi}")

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
)

PRESETS: Dict[str, RasterPreset] = {
    "web-preview": DEFAULT_PRESET,

    # Stubbed for future API milestones — architecture is ready, just activate:
    "web-thumbnail": RasterPreset(
        name="web-thumbnail",
        format="webp",
        dpi=72,
        background_color="#FFFFFF",
        color_mode="contrast-safe",
        padding_percent=0.03,
        max_dimension=512,
    ),
    "ai-vision": RasterPreset(
        name="ai-vision",
        format="png",
        dpi=300,
        background_color="#FFFFFF",
        color_mode="contrast-safe",
        padding_percent=0.02,
        max_dimension=None,
    ),
    "cad-dark-modelspace": RasterPreset(
        name="cad-dark-modelspace",
        format="png",
        dpi=150,
        background_color="#1E1E1E",
        color_mode="aci",
        padding_percent=0.02,
        max_dimension=None,
    ),
    "architectural-monochrome": RasterPreset(
        name="architectural-monochrome",
        format="png",
        dpi=300,
        background_color="#FFFFFF",
        color_mode="monochrome",
        padding_percent=0.02,
        max_dimension=None,
    ),
}
