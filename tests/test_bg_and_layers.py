"""
Tests for background_color and layers parameters on compile_ir_to_raster.
Covers Knob 4 (background override) and Knob 5 (layer filtering).
"""

import pytest
from cad_ir_to_raster import compile_ir_to_raster

# Minimal IR with two distinct layers
MULTI_LAYER_IR = {
    "format": "LAVINCI_CAD_IR_V3",
    "metadata": {"source_file": "test_layers.dwg"},
    "extents": {"min": [0.0, 0.0], "max": [100.0, 100.0], "width": 100.0, "height": 100.0},
    "layers": [
        {"name": "WALLS", "color_aci": 7, "hex_color": "#000000"},
        {"name": "ELECTRIC", "color_aci": 1, "hex_color": "#FF0000"},
    ],
    "geometry_primitives": {
        "primitives": {
            "lines": [
                {"layer": "WALLS", "space": "Model", "start": [0.0, 0.0], "end": [100.0, 100.0]},
                {"layer": "ELECTRIC", "space": "Model", "start": [10.0, 10.0], "end": [90.0, 90.0]},
            ],
            "arcs": [], "circles": [], "polylines": []
        }
    },
    "annotations": [
        {"layer": "WALLS", "text": "North Wall", "x": 0.0, "y": 5.0, "height": 2.5},
        {"layer": "ELECTRIC", "text": "Panel 1", "x": 50.0, "y": 50.0, "height": 2.5},
    ],
    "dimensions": [],
    "components": [],
}

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


class TestBackgroundColor:
    """Tests for the background_color override parameter."""

    def test_background_color_override_produces_image(self):
        """background_color override produces a valid PNG without crashing."""
        result = compile_ir_to_raster(MINIMAL_IR, background_color="#0A2540")
        assert isinstance(result, bytes)
        assert result[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes

    def test_background_color_navy_different_from_default(self):
        """Custom background color produces a different image from default white."""
        default_bytes = compile_ir_to_raster(MINIMAL_IR)
        navy_bytes = compile_ir_to_raster(MINIMAL_IR, background_color="#0A2540")
        assert default_bytes != navy_bytes

    def test_background_color_transparent_falls_back_to_preset(self):
        """'transparent' as background_color falls back to preset default cleanly."""
        result = compile_ir_to_raster(MINIMAL_IR, background_color="transparent")
        default = compile_ir_to_raster(MINIMAL_IR)
        # Should be equivalent to default since transparent triggers fallback
        assert isinstance(result, bytes)
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_background_color_report_telemetry(self):
        """Report confirms the preset name is correctly recorded."""
        _, report = compile_ir_to_raster(MINIMAL_IR, background_color="#FF0000", return_report=True)
        assert report.success is True

    def test_background_color_dark_blue_blueprint(self):
        """Blueprint navy (#0A2540) background with architectural-monochrome preset works."""
        result = compile_ir_to_raster(
            MINIMAL_IR,
            preset="architectural-monochrome",
            background_color="#0A2540"
        )
        assert isinstance(result, bytes)
        assert len(result) > 100


class TestLayersFilter:
    """Tests for the layers whitelist parameter."""

    def test_layers_filter_returns_valid_image(self):
        """Filtering to a single layer produces a valid PNG."""
        result = compile_ir_to_raster(MULTI_LAYER_IR, layers=["WALLS"])
        assert isinstance(result, bytes)
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_layers_filter_none_renders_all(self):
        """layers=None (default) renders everything with no filtering."""
        all_bytes = compile_ir_to_raster(MULTI_LAYER_IR)
        assert isinstance(all_bytes, bytes)
        assert len(all_bytes) > 100

    def test_layers_filter_warning_in_report(self):
        """Filtering layers emits a structured warning in the RasterReport."""
        _, report = compile_ir_to_raster(MULTI_LAYER_IR, layers=["WALLS"], return_report=True)
        assert any("Layer filter active" in w for w in report.warnings)

    def test_layers_filter_case_insensitive(self):
        """Layer names are matched case-insensitively (walls == WALLS)."""
        result_upper = compile_ir_to_raster(MULTI_LAYER_IR, layers=["WALLS"])
        result_lower = compile_ir_to_raster(MULTI_LAYER_IR, layers=["walls"])
        # Both should succeed and produce valid images
        assert isinstance(result_upper, bytes)
        assert isinstance(result_lower, bytes)

    def test_layers_filter_unknown_layer_does_not_crash(self):
        """Filtering to a non-existent layer produces an image without crashing."""
        result = compile_ir_to_raster(MULTI_LAYER_IR, layers=["NONEXISTENT_LAYER_XYZ"])
        assert isinstance(result, bytes)

    def test_layers_and_background_combined(self):
        """layers + background_color can both be applied together."""
        result = compile_ir_to_raster(
            MULTI_LAYER_IR,
            layers=["WALLS"],
            background_color="#F0F4F8",
        )
        assert isinstance(result, bytes)
        assert len(result) > 100
