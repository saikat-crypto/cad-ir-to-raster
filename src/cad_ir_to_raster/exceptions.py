"""
exceptions.py - Developer-Friendly Custom Exception Hierarchy for cad-ir-to-raster.

All exceptions inherit from CadRasterError so callers can catch either specific
error types or the entire family with a single `except CadRasterError`.

Design philosophy:
  Every message tells the developer:
    1. WHAT went wrong (the bad value they gave)
    2. WHAT is expected (valid values or ranges)
    3. HOW to fix it (a concrete example or suggestion)
"""

from __future__ import annotations
from typing import Optional


class CadRasterError(ValueError):
    """
    Base exception for all cad-ir-to-raster errors.
    Inherits from ValueError for broad standard-library compatibility,
    allowing callers to catch either specific errors, CadRasterError, or ValueError.

    Catch this class to handle any error from the engine:

        try:
            compile_ir_to_raster(ir, preset="my-preset")
        except CadRasterError as e:
            print(f"CAD raster error: {e}")
    """


class InvalidPresetError(CadRasterError):
    """
    Raised when an unrecognised preset name is passed.

    Example:
        compile_ir_to_raster(ir, preset="blueprint-mode")
        # -> InvalidPresetError: Unknown preset 'blueprint-mode'. ...
    """
    def __init__(self, name: str, available: list, suggestion: Optional[str] = None):
        hint = f" Did you mean '{suggestion}'?" if suggestion else ""
        super().__init__(
            f"Unknown preset '{name}'.{hint}\n"
            f"  Available presets: {available}\n"
            f"  Example: compile_ir_to_raster(ir, preset='web-preview')"
        )
        self.preset_name = name
        self.available = available


class InvalidFormatError(CadRasterError):
    """
    Raised when an unsupported output format string is provided.

    Example:
        compile_ir_to_raster(ir, format="bmp")
        # -> InvalidFormatError: Unknown format 'bmp'. ...
    """
    SUPPORTED = ("png", "jpeg", "webp")

    def __init__(self, fmt: str):
        super().__init__(
            f"Unknown format '{fmt}'. Supported formats are: {list(self.SUPPORTED)}.\n"
            f"  Example: compile_ir_to_raster(ir, format='png')\n"
            f"  Note: 'jpg' is accepted as an alias for 'jpeg'."
        )
        self.format = fmt


class InvalidDpiError(CadRasterError):
    """
    Raised when DPI is out of the safe rendering range.

    Example:
        compile_ir_to_raster(ir, dpi=9999)
        # -> InvalidDpiError: DPI 9999 is out of range. ...
    """
    MIN_DPI = 1
    MAX_DPI = 1200

    def __init__(self, dpi: int):
        super().__init__(
            f"DPI {dpi} is out of the valid range [{self.MIN_DPI}–{self.MAX_DPI}].\n"
            f"  Recommended values: 72 (thumbnail), 150 (web preview), 300 (AI vision / print).\n"
            f"  Example: compile_ir_to_raster(ir, dpi=150)"
        )
        self.dpi = dpi


class InvalidColorError(CadRasterError):
    """
    Raised when a background_color string is not a valid hex color.

    Example:
        compile_ir_to_raster(ir, background_color="blue")
        # -> InvalidColorError: 'blue' is not a valid hex color. ...
    """
    def __init__(self, color: str, param: str = "background_color"):
        super().__init__(
            f"'{color}' is not a valid color for '{param}'.\n"
            f"  Colors must be 6-character hex strings: '#FFFFFF' (white), '#000000' (black),\n"
            f"  '#1E1E1E' (dark modelspace), '#0A2540' (blueprint navy).\n"
            f"  To use the preset's default background, omit the parameter or pass None.\n"
            f"  To produce a transparent PNG, pass background_color='transparent'."
        )
        self.color = color
        self.param = param


class InvalidIrPayloadError(CadRasterError):
    """
    Raised when the IR source cannot be parsed into a valid dict.

    Example:
        compile_ir_to_raster(None)
        # -> InvalidIrPayloadError: Could not parse the CAD IR payload. ...
    """
    def __init__(self, source_type: type, detail: str = ""):
        extra = f"\n  Detail: {detail}" if detail else ""
        super().__init__(
            f"Could not parse the CAD IR payload from source type '{source_type.__name__}'.{extra}\n"
            f"  Expected one of:\n"
            f"    • A Python dict: {{'format': 'LAVINCI_CAD_IR_V3', ...}}\n"
            f"    • A file path string: '/path/to/drawing_ir.json'\n"
            f"    • A pathlib.Path object: Path('drawing_ir.json')\n"
            f"    • A raw JSON string: '{{\"format\": \"LAVINCI_CAD_IR_V3\", ...}}'\n"
            f"    • A Pydantic model with .model_dump() support\n"
            f"  Tip: Run cad-extractor-ir on your DWG file to generate a valid IR JSON."
        )
        self.source_type = source_type


class InvalidLayerError(CadRasterError):
    """
    Raised when layers parameter is provided but contains no valid entries.

    Note: This is a WARNING-level error. Normally, non-existent layers just silently
    produce an empty (but valid) image. This is raised only if the layers list
    itself is malformed (e.g., not a list, or contains non-string entries).

    Example:
        compile_ir_to_raster(ir, layers="WALLS")   # string instead of list
        # -> InvalidLayerError: 'layers' must be a list of strings. ...
    """
    def __init__(self, layers_value):
        super().__init__(
            f"Invalid 'layers' parameter: got {type(layers_value).__name__} '{layers_value}'.\n"
            f"  'layers' must be a list of layer name strings (case-insensitive), or None.\n"
            f"  Example: compile_ir_to_raster(ir, layers=['WALLS', 'DOORS'])\n"
            f"  Tip: If a layer name doesn't exist in the drawing, it is silently skipped\n"
            f"       and a warning is added to RasterReport.warnings."
        )
        self.layers_value = layers_value
