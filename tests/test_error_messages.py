"""
test_error_messages.py - Developer-friendly error message tests for cad-ir-to-raster.

Verifies that every invalid input produces:
  1. The correct custom exception type (not a bare Python error)
  2. An actionable, human-readable error message with the bad value + valid options + fix hint
  3. Correct exception hierarchy (all inherit from CadRasterError)
"""

import pytest
from cad_ir_to_raster import (
    compile_ir_to_raster,
    CadRasterError,
    InvalidPresetError,
    InvalidFormatError,
    InvalidDpiError,
    InvalidColorError,
    InvalidIrPayloadError,
    InvalidLayerError,
)

MINIMAL_IR = {
    "format": "LAVINCI_CAD_IR_V3",
    "metadata": {"source_file": "test.dwg"},
    "extents": {"min": [0.0, 0.0], "max": [100.0, 75.0], "width": 100.0, "height": 75.0},
    "layers": [{"name": "0", "color_aci": 7, "hex_color": "#000000"}],
    "geometry_primitives": {
        "primitives": {
            "lines": [{"layer": "0", "space": "Model", "start": [0.0, 0.0], "end": [100.0, 75.0]}],
            "arcs": [], "circles": [], "polylines": []
        }
    },
}


class TestExceptionHierarchy:
    """All custom exceptions must be catchable as CadRasterError."""

    def test_invalid_preset_is_cad_raster_error(self):
        with pytest.raises(CadRasterError):
            compile_ir_to_raster(MINIMAL_IR, preset="nonexistent-preset")

    def test_invalid_format_is_cad_raster_error(self):
        with pytest.raises(CadRasterError):
            compile_ir_to_raster(MINIMAL_IR, format="bmp")

    def test_invalid_dpi_is_cad_raster_error(self):
        with pytest.raises(CadRasterError):
            compile_ir_to_raster(MINIMAL_IR, dpi=9999)

    def test_invalid_color_is_cad_raster_error(self):
        with pytest.raises(CadRasterError):
            compile_ir_to_raster(MINIMAL_IR, background_color="blue")

    def test_invalid_ir_is_cad_raster_error(self):
        with pytest.raises(CadRasterError):
            compile_ir_to_raster(None)

    def test_invalid_layers_type_is_cad_raster_error(self):
        with pytest.raises(CadRasterError):
            compile_ir_to_raster(MINIMAL_IR, layers="WALLS")  # string, not list


class TestInvalidPresetError:
    """Preset name typos produce helpful messages with 'did you mean?' suggestions."""

    def test_unknown_preset_raises_invalid_preset_error(self):
        with pytest.raises(InvalidPresetError):
            compile_ir_to_raster(MINIMAL_IR, preset="blueprint-mode")

    def test_error_message_contains_bad_name(self):
        with pytest.raises(InvalidPresetError) as exc_info:
            compile_ir_to_raster(MINIMAL_IR, preset="blueprint-mode")
        assert "blueprint-mode" in str(exc_info.value)

    def test_error_message_contains_available_presets(self):
        with pytest.raises(InvalidPresetError) as exc_info:
            compile_ir_to_raster(MINIMAL_IR, preset="blueprint-mode")
        msg = str(exc_info.value)
        assert "web-preview" in msg

    def test_underscore_typo_suggests_hyphen_version(self):
        """'web_preview' (underscore) should suggest 'web-preview' (hyphen)."""
        with pytest.raises(InvalidPresetError) as exc_info:
            compile_ir_to_raster(MINIMAL_IR, preset="web_preview")
        assert "web-preview" in str(exc_info.value)

    def test_did_you_mean_suggestion_in_message(self):
        """Fuzzy match on 'cad_dark' suggests 'cad-dark-modelspace'."""
        with pytest.raises(InvalidPresetError) as exc_info:
            compile_ir_to_raster(MINIMAL_IR, preset="cad_dark")
        assert "Did you mean" in str(exc_info.value)

    def test_invalid_preset_exposes_name_attribute(self):
        """InvalidPresetError.preset_name captures the bad value for programmatic access."""
        with pytest.raises(InvalidPresetError) as exc_info:
            compile_ir_to_raster(MINIMAL_IR, preset="my-typo")
        assert exc_info.value.preset_name == "my-typo"

    def test_invalid_preset_exposes_available_attribute(self):
        """InvalidPresetError.available lists all valid preset names."""
        with pytest.raises(InvalidPresetError) as exc_info:
            compile_ir_to_raster(MINIMAL_IR, preset="garbage")
        assert "web-preview" in exc_info.value.available


class TestInvalidFormatError:
    """Unsupported format strings produce clear messages."""

    def test_bmp_raises_invalid_format(self):
        with pytest.raises(InvalidFormatError):
            compile_ir_to_raster(MINIMAL_IR, format="bmp")

    def test_tiff_raises_invalid_format(self):
        with pytest.raises(InvalidFormatError):
            compile_ir_to_raster(MINIMAL_IR, format="tiff")

    def test_error_message_contains_bad_format(self):
        with pytest.raises(InvalidFormatError) as exc_info:
            compile_ir_to_raster(MINIMAL_IR, format="bmp")
        assert "bmp" in str(exc_info.value)

    def test_error_message_contains_valid_formats(self):
        with pytest.raises(InvalidFormatError) as exc_info:
            compile_ir_to_raster(MINIMAL_IR, format="bmp")
        msg = str(exc_info.value)
        assert "png" in msg
        assert "jpeg" in msg
        assert "webp" in msg

    def test_jpg_alias_accepted_without_error(self):
        """'jpg' is a valid alias for 'jpeg' and must NOT raise."""
        result = compile_ir_to_raster(MINIMAL_IR, format="jpg")
        assert isinstance(result, bytes)
        assert result[:2] == b"\xff\xd8"  # JPEG magic


class TestInvalidDpiError:
    """Out-of-range DPI values produce clear messages with valid range."""

    def test_dpi_zero_raises(self):
        with pytest.raises(InvalidDpiError):
            compile_ir_to_raster(MINIMAL_IR, dpi=0)

    def test_dpi_9999_raises(self):
        with pytest.raises(InvalidDpiError):
            compile_ir_to_raster(MINIMAL_IR, dpi=9999)

    def test_error_message_contains_bad_dpi(self):
        with pytest.raises(InvalidDpiError) as exc_info:
            compile_ir_to_raster(MINIMAL_IR, dpi=5000)
        assert "5000" in str(exc_info.value)

    def test_error_message_contains_valid_range(self):
        with pytest.raises(InvalidDpiError) as exc_info:
            compile_ir_to_raster(MINIMAL_IR, dpi=5000)
        msg = str(exc_info.value)
        assert "1200" in msg

    def test_dpi_1_accepted_without_error(self):
        """DPI 1 is the minimum valid DPI."""
        result = compile_ir_to_raster(MINIMAL_IR, dpi=1)
        assert isinstance(result, bytes)

    @pytest.mark.filterwarnings("ignore::PIL.Image.DecompressionBombWarning")
    def test_dpi_1200_accepted_without_error(self):
        """DPI 1200 is the maximum valid DPI."""
        tiny_ir = {
            "format": "LAVINCI_CAD_IR_V3",
            "extents": {"min": [0.0, 0.0], "max": [1.0, 1.0], "width": 1.0, "height": 1.0},
            "geometry_primitives": {
                "primitives": {
                    "lines": [{"layer": "0", "space": "Model", "start": [0.0, 0.0], "end": [1.0, 1.0]}],
                    "arcs": [], "circles": [], "polylines": []
                }
            },
        }
        result = compile_ir_to_raster(tiny_ir, dpi=1200)
        assert isinstance(result, bytes)


class TestInvalidColorError:
    """Non-hex background_color values produce clear messages with examples."""

    def test_named_color_blue_raises(self):
        with pytest.raises(InvalidColorError):
            compile_ir_to_raster(MINIMAL_IR, background_color="blue")

    def test_rgb_function_raises(self):
        with pytest.raises(InvalidColorError):
            compile_ir_to_raster(MINIMAL_IR, background_color="rgb(255,255,255)")

    def test_error_message_contains_bad_color(self):
        with pytest.raises(InvalidColorError) as exc_info:
            compile_ir_to_raster(MINIMAL_IR, background_color="navy")
        assert "navy" in str(exc_info.value)

    def test_error_message_contains_fix_examples(self):
        with pytest.raises(InvalidColorError) as exc_info:
            compile_ir_to_raster(MINIMAL_IR, background_color="navy")
        assert "#FFFFFF" in str(exc_info.value)

    def test_valid_6char_hex_accepted(self):
        result = compile_ir_to_raster(MINIMAL_IR, background_color="#0A2540")
        assert isinstance(result, bytes)

    def test_transparent_keyword_accepted(self):
        result = compile_ir_to_raster(MINIMAL_IR, background_color="transparent")
        assert isinstance(result, bytes)


class TestInvalidIrPayloadError:
    """None and non-parseable inputs produce clear messages pointing to correct format."""

    def test_none_ir_raises(self):
        with pytest.raises(InvalidIrPayloadError):
            compile_ir_to_raster(None)

    def test_integer_ir_raises(self):
        with pytest.raises(InvalidIrPayloadError):
            compile_ir_to_raster(12345)

    def test_error_message_contains_type_info(self):
        with pytest.raises(InvalidIrPayloadError) as exc_info:
            compile_ir_to_raster(None)
        assert "NoneType" in str(exc_info.value)

    def test_error_message_mentions_expected_types(self):
        with pytest.raises(InvalidIrPayloadError) as exc_info:
            compile_ir_to_raster(None)
        msg = str(exc_info.value)
        assert "dict" in msg or "JSON" in msg

    def test_nonexistent_file_path_raises(self):
        with pytest.raises(InvalidIrPayloadError):
            compile_ir_to_raster("/nonexistent/path/drawing_ir.json")


class TestInvalidLayerError:
    """Non-list 'layers' parameter produces clear message with usage example."""

    def test_string_layers_raises(self):
        """Passing a bare string instead of a list must raise InvalidLayerError."""
        with pytest.raises(InvalidLayerError):
            compile_ir_to_raster(MINIMAL_IR, layers="WALLS")

    def test_int_layers_raises(self):
        with pytest.raises(InvalidLayerError):
            compile_ir_to_raster(MINIMAL_IR, layers=42)

    def test_error_message_contains_bad_value(self):
        with pytest.raises(InvalidLayerError) as exc_info:
            compile_ir_to_raster(MINIMAL_IR, layers="WALLS")
        assert "WALLS" in str(exc_info.value)

    def test_error_message_shows_correct_usage(self):
        with pytest.raises(InvalidLayerError) as exc_info:
            compile_ir_to_raster(MINIMAL_IR, layers="WALLS")
        assert "list" in str(exc_info.value).lower()

    def test_empty_list_layers_does_not_raise(self):
        """Empty list is a no-op (render all layers), not an error."""
        result = compile_ir_to_raster(MINIMAL_IR, layers=[])
        assert isinstance(result, bytes)

    def test_valid_list_layers_does_not_raise(self):
        result = compile_ir_to_raster(MINIMAL_IR, layers=["0", "WALLS"])
        assert isinstance(result, bytes)
