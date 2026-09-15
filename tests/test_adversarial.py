"""
test_adversarial.py — Adversarial edge case tests for cad-ir-to-raster.
Verifies the engine never crashes or raises unhandled exceptions on:
  - Empty drawings
  - NaN/Inf coordinates
  - Zero or missing geometry
  - Malformed metadata
  - Degenerate primitives
"""

import math
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "cad-ir-to-svg" / "src"))

from cad_ir_to_raster import compile_ir_to_raster


def _base_ir(**overrides):
    ir = {
        "format": "LAVINCI_CAD_IR_V3",
        "metadata": {"source_file": "adv.dxf", "dxf_version": "AC1021",
                     "cad_version": "AutoCAD 2007", "units": 4,
                     "measurement_system": "metric"},
        "extents": {"min": [0.0, 0.0], "max": [100.0, 75.0], "width": 100.0, "height": 75.0},
        "layers": [{"name": "0", "color_aci": 7, "hex_color": "#000000",
                    "is_off": False, "is_locked": False, "is_frozen": False, "linetype": "Continuous"}],
        "bill_of_materials": {},
        "block_definitions": {},
        "components": [],
        "annotations": [],
        "dimensions": [],
        "geometry_primitives": {
            "summary": {"total_lines": 0, "total_arcs": 0, "total_circles": 0,
                        "total_polylines": 0, "total_components": 0,
                        "total_annotations": 0, "total_dimensions": 0, "total_block_definitions": 0},
            "primitives": {"lines": [], "arcs": [], "circles": [], "polylines": []}
        }
    }
    ir.update(overrides)
    return ir


def _assert_valid_png(data):
    """Asserts that bytes is a valid PNG blob."""
    assert isinstance(data, bytes), f"Expected bytes, got {type(data)}"
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "Not a valid PNG (bad magic bytes)"
    assert len(data) > 100, f"PNG suspiciously small: {len(data)} bytes"


class TestAdversarialCases(unittest.TestCase):

    def test_completely_empty_ir_dict(self):
        """Empty dict {} compiles without crashing, producing a valid PNG."""
        result = compile_ir_to_raster({})
        _assert_valid_png(result)

    def test_empty_geometry_produces_blank_page(self):
        """IR with zero primitives compiles to a valid blank PNG page."""
        ir = _base_ir()
        result = compile_ir_to_raster(ir)
        _assert_valid_png(result)

    def test_nan_line_coordinates_do_not_crash(self):
        """Lines with NaN coordinates are silently dropped; engine does not crash."""
        ir = _base_ir()
        ir["geometry_primitives"]["primitives"]["lines"] = [
            {"layer": "0", "space": "Model", "start": [float("nan"), 0.0], "end": [100.0, 0.0]},
            {"layer": "0", "space": "Model", "start": [0.0, float("nan")], "end": [100.0, 50.0]},
        ]
        result = compile_ir_to_raster(ir)
        _assert_valid_png(result)

    def test_inf_line_coordinates_do_not_crash(self):
        """Lines with Inf coordinates are silently dropped; engine does not crash."""
        ir = _base_ir()
        ir["geometry_primitives"]["primitives"]["lines"] = [
            {"layer": "0", "space": "Model", "start": [float("inf"), 0.0], "end": [50.0, 50.0]},
            {"layer": "0", "space": "Model", "start": [0.0, 0.0], "end": [float("-inf"), 50.0]},
        ]
        result = compile_ir_to_raster(ir)
        _assert_valid_png(result)

    def test_zero_radius_circle_does_not_crash(self):
        """Circles with zero or negative radius are silently dropped."""
        ir = _base_ir()
        ir["geometry_primitives"]["primitives"]["circles"] = [
            {"layer": "0", "space": "Model", "center": [50.0, 37.5], "radius": 0.0},
            {"layer": "0", "space": "Model", "center": [50.0, 37.5], "radius": -10.0},
        ]
        result = compile_ir_to_raster(ir)
        _assert_valid_png(result)

    def test_missing_metadata_does_not_crash(self):
        """Missing metadata fields are gracefully handled."""
        ir = {"format": "LAVINCI_CAD_IR_V3",
              "geometry_primitives": {"primitives": {"lines": [], "arcs": [], "circles": [], "polylines": []}}}
        result = compile_ir_to_raster(ir)
        _assert_valid_png(result)

    def test_null_layers_does_not_crash(self):
        """Null or missing layers dict is handled gracefully."""
        ir = _base_ir()
        ir["layers"] = None
        result = compile_ir_to_raster(ir)
        _assert_valid_png(result)

    def test_extreme_scale_drawing_does_not_crash(self):
        """Extremely large coordinates (near 1e6) do not cause divide by zero or crash."""
        ir = _base_ir()
        ir["geometry_primitives"]["primitives"]["lines"] = [
            {"layer": "0", "space": "Model", "start": [0.0, 0.0], "end": [999999.0, 999999.0]},
        ]
        result = compile_ir_to_raster(ir)
        _assert_valid_png(result)

    def test_sub_micron_drawing_does_not_crash(self):
        """Extremely small coordinate spans do not cause crash."""
        ir = _base_ir()
        ir["geometry_primitives"]["primitives"]["lines"] = [
            {"layer": "0", "space": "Model", "start": [0.0, 0.0], "end": [0.000001, 0.000001]},
        ]
        result = compile_ir_to_raster(ir)
        _assert_valid_png(result)

    def test_non_list_primitives_does_not_crash(self):
        """Non-list primitive collections (e.g., integer value) do not crash the engine."""
        ir = _base_ir()
        ir["geometry_primitives"]["primitives"]["lines"] = 999
        ir["geometry_primitives"]["primitives"]["circles"] = "not-a-list"
        result = compile_ir_to_raster(ir)
        _assert_valid_png(result)

    def test_large_annotation_count_does_not_crash(self):
        """Drawing with many annotations compiles without crashing."""
        ir = _base_ir()
        ir["annotations"] = [
            {"type": "TEXT", "layer": "0", "space": "Model",
             "raw_text": f"Label {i}", "clean_text": f"Label {i}",
             "position": [float(i % 100), float(i // 100)], "height": 2.5}
            for i in range(500)
        ]
        result = compile_ir_to_raster(ir)
        _assert_valid_png(result)


if __name__ == "__main__":
    unittest.main()
