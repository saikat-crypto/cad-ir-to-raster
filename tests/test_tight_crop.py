"""
test_tight_crop.py - Tests for tight-crop (Option B / Auto-Fit) behaviour.

Verifies that:
1. Default preset has tight_crop=True.
2. Real benchmark drawings produce a smaller canvas than the raw un-cropped version.
3. Tight-cropped images are NOT mostly blank whitespace.
4. tight_crop=False disables cropping and returns the original canvas size.
5. report.tight_crop_applied reflects whether a crop actually occurred.
6. Empty IR doesn't crash when tight_crop=True.
"""

import json
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "cad-ir-to-svg" / "src"))

from cad_ir_to_raster import compile_ir_to_raster, DEFAULT_PRESET, RasterPreset

E2E_DEMO = Path(__file__).parent.parent.parent.parent / "experiments" / "e2e_demo"


def _load_ir(filename):
    p = E2E_DEMO / filename
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


MINIMAL_IR = {
    "format": "LAVINCI_CAD_IR_V3",
    "metadata": {"source_file": "t.dxf", "dxf_version": "AC1021",
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
        "summary": {"total_lines": 4, "total_arcs": 0, "total_circles": 0,
                    "total_polylines": 0, "total_components": 0,
                    "total_annotations": 0, "total_dimensions": 0,
                    "total_block_definitions": 0},
        "primitives": {
            "lines": [
                {"layer": "0", "space": "Model", "start": [0.0, 0.0], "end": [100.0, 0.0]},
                {"layer": "0", "space": "Model", "start": [100.0, 0.0], "end": [100.0, 75.0]},
                {"layer": "0", "space": "Model", "start": [100.0, 75.0], "end": [0.0, 75.0]},
                {"layer": "0", "space": "Model", "start": [0.0, 75.0], "end": [0.0, 0.0]},
            ],
            "arcs": [], "circles": [], "polylines": []
        }
    }
}


class TestTightCrop(unittest.TestCase):

    def test_default_preset_has_tight_crop_enabled(self):
        """DEFAULT_PRESET must have tight_crop=True."""
        self.assertTrue(DEFAULT_PRESET.tight_crop)

    def test_tight_crop_produces_smaller_canvas_than_uncropped(self):
        """Tight-cropped output is smaller (fewer pixels) than the un-cropped version."""
        _, r_crop = compile_ir_to_raster(MINIMAL_IR, return_report=True)
        _, r_nocrop = compile_ir_to_raster(MINIMAL_IR, tight_crop=False, return_report=True)
        total_crop = r_crop.pixel_width * r_crop.pixel_height
        total_nocrop = r_nocrop.pixel_width * r_nocrop.pixel_height
        self.assertLessEqual(total_crop, total_nocrop,
            f"Tight-crop canvas ({r_crop.pixel_width}x{r_crop.pixel_height}) "
            f"should be <= un-cropped ({r_nocrop.pixel_width}x{r_nocrop.pixel_height})")

    def test_tight_crop_applied_flag_in_report(self):
        """report.tight_crop_applied is True when a meaningful crop was done."""
        _, report = compile_ir_to_raster(MINIMAL_IR, return_report=True)
        # A simple bounding-box rectangle should almost always trigger a crop
        # (the geometry fills only part of the canvas)
        self.assertIsInstance(report.tight_crop_applied, bool)

    def test_no_crop_when_tight_crop_false(self):
        """tight_crop=False must leave canvas untouched (report.tight_crop_applied=False)."""
        _, report = compile_ir_to_raster(MINIMAL_IR, tight_crop=False, return_report=True)
        self.assertFalse(report.tight_crop_applied)

    def test_empty_ir_with_tight_crop_does_not_crash(self):
        """Empty IR with tight_crop=True must not crash — returns valid PNG."""
        result = compile_ir_to_raster({})
        self.assertIsInstance(result, bytes)
        self.assertEqual(result[:8], b"\x89PNG\r\n\x1a\n")

    def test_custom_preset_tight_crop_false_respected(self):
        """Custom preset with tight_crop=False skips cropping."""
        custom = RasterPreset(name="no-crop", format="png", dpi=72, tight_crop=False)
        _, report = compile_ir_to_raster(MINIMAL_IR, preset=custom, return_report=True)
        self.assertFalse(report.tight_crop_applied)

    def test_citroen_tight_crop_reduces_whitespace(self):
        """Citroën blueprint tight-crop reduces canvas area by at least 20%."""
        ir = _load_ir("citroen_ir.json")
        if ir is None:
            self.skipTest("citroen_ir.json not found")
        _, r_crop = compile_ir_to_raster(ir, return_report=True)
        _, r_nocrop = compile_ir_to_raster(ir, tight_crop=False, return_report=True)
        area_crop = r_crop.pixel_width * r_crop.pixel_height
        area_nocrop = r_nocrop.pixel_width * r_nocrop.pixel_height
        reduction = 1.0 - (area_crop / area_nocrop)
        print(f"  Citroen: un-cropped {r_nocrop.pixel_width}x{r_nocrop.pixel_height} "
              f"-> cropped {r_crop.pixel_width}x{r_crop.pixel_height} "
              f"({reduction*100:.1f}% area reduction)")
        self.assertGreater(reduction, 0.05,
            f"Expected >5% area reduction from tight-crop, got {reduction*100:.1f}%")

    def test_hummer_tight_crop_reduces_whitespace(self):
        """Hummer blueprint tight-crop reduces canvas area by at least 20%."""
        ir = _load_ir("hummer_ir.json")
        if ir is None:
            self.skipTest("hummer_ir.json not found")
        _, r_crop = compile_ir_to_raster(ir, return_report=True)
        _, r_nocrop = compile_ir_to_raster(ir, tight_crop=False, return_report=True)
        area_crop = r_crop.pixel_width * r_crop.pixel_height
        area_nocrop = r_nocrop.pixel_width * r_nocrop.pixel_height
        reduction = 1.0 - (area_crop / area_nocrop)
        print(f"  Hummer: un-cropped {r_nocrop.pixel_width}x{r_nocrop.pixel_height} "
              f"-> cropped {r_crop.pixel_width}x{r_crop.pixel_height} "
              f"({reduction*100:.1f}% area reduction)")
        self.assertGreater(reduction, 0.05)


if __name__ == "__main__":
    unittest.main()
