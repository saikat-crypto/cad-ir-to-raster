"""
test_compiler.py — Core compilation tests for cad-ir-to-raster.

Tests:
  1. Minimal IR compiles to valid PNG file on disk.
  2. In-memory bytes mode (output_path=None) returns valid PNG headers.
  3. JPEG encoding works (JPEG magic bytes FF D8 FF).
  4. WebP encoding works (RIFF....WEBP magic).
  5. RasterReport fields are correctly populated.
  6. compile_ir_to_raster accepts file path, dict, and JSON string.
"""

import json
import struct
import unittest
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "cad-ir-to-svg" / "src"))

from cad_ir_to_raster import compile_ir_to_raster, DEFAULT_PRESET, RasterReport


# ── Shared fixture ────────────────────────────────────────────────────────────

MINIMAL_IR = {
    "format": "LAVINCI_CAD_IR_V3",
    "metadata": {"source_file": "test.dxf", "dxf_version": "AC1021",
                 "cad_version": "AutoCAD 2007", "units": 4,
                 "measurement_system": "metric"},
    "extents": {"min": [0.0, 0.0], "max": [100.0, 75.0], "width": 100.0, "height": 75.0},
    "layers": [
        {"name": "0", "color_aci": 7, "hex_color": "#000000",
         "is_off": False, "is_locked": False, "is_frozen": False, "linetype": "Continuous"}
    ],
    "bill_of_materials": {},
    "block_definitions": {},
    "components": [],
    "annotations": [],
    "dimensions": [],
    "geometry_primitives": {
        "summary": {
            "total_lines": 4, "total_arcs": 1, "total_circles": 1,
            "total_polylines": 0, "total_components": 0,
            "total_annotations": 0, "total_dimensions": 0, "total_block_definitions": 0
        },
        "primitives": {
            "lines": [
                {"layer": "0", "space": "Model", "start": [0.0, 0.0], "end": [100.0, 0.0]},
                {"layer": "0", "space": "Model", "start": [100.0, 0.0], "end": [100.0, 75.0]},
                {"layer": "0", "space": "Model", "start": [100.0, 75.0], "end": [0.0, 75.0]},
                {"layer": "0", "space": "Model", "start": [0.0, 75.0], "end": [0.0, 0.0]},
            ],
            "arcs": [
                {"layer": "0", "space": "Model", "center": [50.0, 37.5],
                 "radius": 20.0, "start_angle": 0.0, "end_angle": 180.0}
            ],
            "circles": [
                {"layer": "0", "space": "Model", "center": [50.0, 37.5], "radius": 10.0}
            ],
            "polylines": []
        }
    }
}


class TestCoreCompilation(unittest.TestCase):

    def test_compile_to_file_produces_png(self):
        """compile_ir_to_raster writes a valid PNG file to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "output.png"
            result = compile_ir_to_raster(MINIMAL_IR, output_path=str(out))
            self.assertIsInstance(result, Path)
            self.assertTrue(out.exists(), "Output PNG file was not created")
            self.assertGreater(out.stat().st_size, 0, "Output PNG file is empty")
            # Verify PNG magic bytes: 89 50 4E 47 0D 0A 1A 0A
            with open(out, "rb") as f:
                header = f.read(8)
            self.assertEqual(header, b"\x89PNG\r\n\x1a\n", "File does not have PNG signature")

    def test_compile_returns_bytes_when_no_output_path(self):
        """compile_ir_to_raster returns raw bytes when output_path is None."""
        result = compile_ir_to_raster(MINIMAL_IR)
        self.assertIsInstance(result, bytes)
        self.assertGreater(len(result), 0)
        self.assertTrue(result[:8] == b"\x89PNG\r\n\x1a\n", "Bytes do not have PNG signature")

    def test_compile_jpeg_produces_valid_jpeg(self):
        """JPEG format outputs correct magic bytes (FF D8 FF)."""
        result = compile_ir_to_raster(MINIMAL_IR, format="jpeg")
        self.assertIsInstance(result, bytes)
        self.assertEqual(result[:2], b"\xff\xd8", "Bytes do not have JPEG signature (FF D8)")

    def test_compile_webp_produces_valid_webp(self):
        """WebP format outputs RIFF....WEBP magic bytes."""
        result = compile_ir_to_raster(MINIMAL_IR, format="webp")
        self.assertIsInstance(result, bytes)
        self.assertEqual(result[:4], b"RIFF", "Bytes do not have RIFF header")
        self.assertEqual(result[8:12], b"WEBP", "Bytes do not have WEBP marker at offset 8")

    def test_return_report_flag(self):
        """return_report=True returns a (result, RasterReport) tuple."""
        result, report = compile_ir_to_raster(MINIMAL_IR, return_report=True)
        self.assertIsInstance(result, bytes)
        self.assertIsInstance(report, RasterReport)
        self.assertTrue(report.success)
        self.assertGreater(report.pixel_width, 0)
        self.assertGreater(report.pixel_height, 0)
        self.assertGreater(report.file_size_bytes, 0)
        self.assertGreater(report.render_time_ms, 0)
        self.assertEqual(report.format, "png")
        self.assertEqual(report.dpi, 150)

    def test_accepts_dict_source(self):
        """Engine accepts a plain Python dict as ir_source."""
        result = compile_ir_to_raster(MINIMAL_IR)
        self.assertIsInstance(result, bytes)
        self.assertGreater(len(result), 0)

    def test_accepts_filepath_source(self):
        """Engine accepts a Path to a JSON file as ir_source."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tf:
            json.dump(MINIMAL_IR, tf)
            tf_path = tf.name
        try:
            result = compile_ir_to_raster(Path(tf_path))
            self.assertIsInstance(result, bytes)
            self.assertGreater(len(result), 0)
        finally:
            import os
            os.unlink(tf_path)

    def test_accepts_json_string_source(self):
        """Engine accepts a raw JSON string as ir_source."""
        json_str = json.dumps(MINIMAL_IR)
        result = compile_ir_to_raster(json_str)
        self.assertIsInstance(result, bytes)
        self.assertGreater(len(result), 0)

    def test_output_has_positive_dimensions(self):
        """Compiled image has positive width and height."""
        _, report = compile_ir_to_raster(MINIMAL_IR, return_report=True)
        self.assertGreater(report.pixel_width, 0)
        self.assertGreater(report.pixel_height, 0)


if __name__ == "__main__":
    unittest.main()
