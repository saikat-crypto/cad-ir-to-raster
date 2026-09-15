"""
test_real_world.py — Real-world blueprint verification for cad-ir-to-raster.

Compiles benchmark IR fixtures (citroen, hummer, mercedes, sample_ir) and
verifies:
  - No crashes or unhandled exceptions.
  - Output is a valid PNG with positive pixel dimensions.
  - Compilation completes within a reasonable time threshold.
  - Generated PNG file has non-trivial byte size (not blank).
"""

import json
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "cad-ir-to-svg" / "src"))

from cad_ir_to_raster import compile_ir_to_raster

E2E_DEMO = Path(__file__).parent.parent.parent.parent / "experiments" / "e2e_demo"

# Maximum allowed compilation time per drawing (seconds)
TIME_LIMIT_SEC = 15.0


def _load_ir(filename):
    p = E2E_DEMO / filename
    if not p.exists():
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _assert_valid_png(data, label):
    assert isinstance(data, bytes), f"[{label}] Expected bytes, got {type(data)}"
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"[{label}] Not valid PNG magic bytes"
    assert len(data) > 500, f"[{label}] PNG too small ({len(data)} bytes), likely blank"


class TestRealWorldBlueprints(unittest.TestCase):

    def _run_benchmark(self, ir_filename, label):
        ir = _load_ir(ir_filename)
        if ir is None:
            self.skipTest(f"Benchmark fixture not found: {ir_filename}")
        import time
        t0 = time.perf_counter()
        result, report = compile_ir_to_raster(ir, return_report=True)
        elapsed = time.perf_counter() - t0
        _assert_valid_png(result, label)
        self.assertTrue(report.success, f"[{label}] report.success is False")
        self.assertGreater(report.pixel_width, 0, f"[{label}] pixel_width <= 0")
        self.assertGreater(report.pixel_height, 0, f"[{label}] pixel_height <= 0")
        self.assertLess(elapsed, TIME_LIMIT_SEC,
                        f"[{label}] compilation took {elapsed:.2f}s (limit {TIME_LIMIT_SEC}s)")
        print(f"  [{label}] {report.pixel_width}x{report.pixel_height}px "
              f"@ {report.dpi} DPI, {report.file_size_bytes:,} bytes, "
              f"{report.render_time_ms:.1f}ms")

    def test_citroen_ir(self):
        self._run_benchmark("citroen_ir.json", "Citroën Blueprint")

    def test_hummer_ir(self):
        self._run_benchmark("hummer_ir.json", "Hummer Blueprint")

    def test_mercedes_ir(self):
        self._run_benchmark("mercedes_ir.json", "Mercedes Blueprint")

    def test_mercedes_300sl_ir(self):
        self._run_benchmark("mercedes_300sl_ir.json", "Mercedes 300SL")

    def test_sample_ir(self):
        # Use the workspace-level sample_ir.json
        sample_path = Path(__file__).parent.parent.parent.parent / "experiments" / "sample_ir.json"
        if not sample_path.exists():
            self.skipTest("sample_ir.json not found")
        with open(sample_path, "r", encoding="utf-8") as f:
            ir = json.load(f)
        import time
        t0 = time.perf_counter()
        result, report = compile_ir_to_raster(ir, return_report=True)
        elapsed = time.perf_counter() - t0
        _assert_valid_png(result, "sample_ir")
        self.assertGreater(report.pixel_width, 0)
        self.assertGreater(report.pixel_height, 0)
        self.assertLess(elapsed, TIME_LIMIT_SEC)
        print(f"  [sample_ir] {report.pixel_width}x{report.pixel_height}px @ {report.dpi} DPI "
              f"{report.file_size_bytes:,} bytes in {report.render_time_ms:.1f}ms")


if __name__ == "__main__":
    unittest.main()
