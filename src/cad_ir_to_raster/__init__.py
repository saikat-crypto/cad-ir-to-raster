"""
cad-ir-to-raster: High-fidelity raster image compiler for LAVINCI_CAD_IR_V3.
Part of the La Vinci / Rine CAD processing ecosystem.
"""

__version__ = "1.0.0"
__author__ = "Saikat Dutta Chowdhury"

from .config import RasterPreset, PRESETS, DEFAULT_PRESET
from .compiler import compile_ir_to_raster, get_raster_dimensions, compile_all_presets_parallel
from .telemetry import RasterReport
from .exceptions import (
    CadRasterError,
    InvalidPresetError,
    InvalidFormatError,
    InvalidDpiError,
    InvalidColorError,
    InvalidIrPayloadError,
    InvalidLayerError,
)

__all__ = [
    # Core API
    "compile_ir_to_raster",
    "get_raster_dimensions",
    "compile_all_presets_parallel",
    # Config
    "RasterPreset",
    "PRESETS",
    "DEFAULT_PRESET",
    # Telemetry
    "RasterReport",
    # Exceptions (catch individually or as CadRasterError base)
    "CadRasterError",
    "InvalidPresetError",
    "InvalidFormatError",
    "InvalidDpiError",
    "InvalidColorError",
    "InvalidIrPayloadError",
    "InvalidLayerError",
]
