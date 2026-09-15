"""
test_presets.py — Preset configuration and DPI scaling tests.
"""

import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "cad-ir-to-svg" / "src"))

from cad_ir_to_raster import compile_ir_to_raster, get_raster_dimensions, PRESETS, DEFAULT_PRESET, RasterPreset


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
        "summary": {"total_lines": 1, "total_arcs": 0, "total_circles": 0,
                    "total_polylines": 0, "total_components": 0,
                    "total_annotations": 0, "total_dimensions": 0, "total_block_definitions": 0},
        "primitives": {
            "lines": [{"layer": "0", "space": "Model", "start": [0.0, 0.0], "end": [100.0, 75.0]}],
            "arcs": [], "circles": [], "polylines": []
        }
    }
}


class TestPresets(unittest.TestCase):

    def test_default_preset_is_web_preview_png_150dpi(self):
        """DEFAULT_PRESET is web-preview, PNG, 150 DPI."""
        self.assertEqual(DEFAULT_PRESET.name, "web-preview")
        self.assertEqual(DEFAULT_PRESET.normalized_format, "png")
        self.assertEqual(DEFAULT_PRESET.dpi, 150)
        self.assertEqual(DEFAULT_PRESET.background_color, "#FFFFFF")

    def test_all_presets_are_registered(self):
        """All expected preset names are present in PRESETS registry."""
        expected = {"web-preview", "web-thumbnail", "ai-vision",
                    "cad-dark-modelspace", "architectural-monochrome"}
        self.assertTrue(expected.issubset(set(PRESETS.keys())))

    def test_dpi_override_scales_dimensions(self):
        """Doubling DPI roughly doubles pixel dimensions."""
        _, r150 = compile_ir_to_raster(MINIMAL_IR, dpi=150, return_report=True)
        _, r300 = compile_ir_to_raster(MINIMAL_IR, dpi=300, return_report=True)
        # 300 DPI should produce roughly 2x dimensions (within 10% tolerance)
        ratio_w = r300.pixel_width / r150.pixel_width
        ratio_h = r300.pixel_height / r150.pixel_height
        self.assertGreater(ratio_w, 1.8, f"Width ratio {ratio_w:.2f} too small (expected ~2.0)")
        self.assertLess(ratio_w, 2.2, f"Width ratio {ratio_w:.2f} too large (expected ~2.0)")
        self.assertGreater(ratio_h, 1.8)
        self.assertLess(ratio_h, 2.2)

    def test_format_override_png_to_jpeg(self):
        """format='jpeg' override produces JPEG bytes regardless of preset default."""
        result = compile_ir_to_raster(MINIMAL_IR, format="jpeg")
        self.assertIsInstance(result, bytes)
        self.assertEqual(result[:2], b"\xff\xd8")

    def test_format_override_png_to_webp(self):
        """format='webp' override produces WebP bytes."""
        result = compile_ir_to_raster(MINIMAL_IR, format="webp")
        self.assertIsInstance(result, bytes)
        self.assertEqual(result[:4], b"RIFF")
        self.assertEqual(result[8:12], b"WEBP")

    def test_preset_by_name_string(self):
        """Passing preset by name string resolves correctly."""
        _, report = compile_ir_to_raster(MINIMAL_IR, preset="web-preview", return_report=True)
        self.assertEqual(report.preset_name, "web-preview")
        self.assertEqual(report.dpi, 150)

    def test_invalid_preset_name_raises(self):
        """Passing unknown preset name raises ValueError."""
        with self.assertRaises(ValueError):
            compile_ir_to_raster(MINIMAL_IR, preset="non-existent-preset")

    def test_custom_raster_preset(self):
        """Passing a custom RasterPreset instance works correctly."""
        custom = RasterPreset(name="custom-test", format="png", dpi=72)
        _, report = compile_ir_to_raster(MINIMAL_IR, preset=custom, return_report=True)
        self.assertEqual(report.dpi, 72)

    def test_get_raster_dimensions_returns_positive_tuple(self):
        """get_raster_dimensions returns (width, height) as positive integers."""
        w, h = get_raster_dimensions(MINIMAL_IR)
        self.assertIsInstance(w, int)
        self.assertIsInstance(h, int)
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)

    def test_max_dimension_cap(self):
        """max_dimension cap constrains the largest axis to the specified pixel limit."""
        capped_preset = RasterPreset(name="test-cap", format="png", dpi=300, max_dimension=512)
        _, report = compile_ir_to_raster(MINIMAL_IR, preset=capped_preset, return_report=True)
        self.assertLessEqual(max(report.pixel_width, report.pixel_height), 512)

    def test_invalid_format_raises_value_error(self):
        """Unsupported format string raises ValueError."""
        with self.assertRaises((ValueError, Exception)):
            compile_ir_to_raster(MINIMAL_IR, format="bmp_unsupported")


if __name__ == "__main__":
    unittest.main()
