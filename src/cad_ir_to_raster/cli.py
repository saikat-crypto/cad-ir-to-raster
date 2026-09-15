"""
cli.py - Command-line interface for cad-ir-to-raster.

Usage:
    cad-ir-to-raster input_ir.json -o output.png
    cad-ir-to-raster input_ir.json -o preview.jpg --format jpeg --dpi 300
    cad-ir-to-raster input_ir.json -o thumb.webp --preset web-thumbnail
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

from .compiler import compile_ir_to_raster
from .config import PRESETS


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="cad-ir-to-raster",
        description="Convert a LAVINCI_CAD_IR_V3 JSON file into a raster image (PNG, JPEG, WebP).",
    )
    parser.add_argument("ir_source", type=str, help="Path to the IR JSON input file.")
    parser.add_argument("-o", "--output", type=str, required=True, help="Output raster image path.")
    parser.add_argument(
        "--preset",
        type=str,
        default="web-preview",
        choices=list(PRESETS.keys()),
        help="Rendering preset name. Default: web-preview",
    )
    parser.add_argument(
        "--format",
        type=str,
        default=None,
        choices=["png", "jpeg", "webp"],
        help="Override output format. Overrides preset format.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=None,
        help="Override DPI. Overrides preset DPI.",
    )

    args = parser.parse_args()
    ir_path = Path(args.ir_source)
    if not ir_path.is_file():
        print(f"Error: IR source file not found: {ir_path}", file=sys.stderr)
        sys.exit(1)

    try:
        out_path, report = compile_ir_to_raster(
            ir_path,
            output_path=args.output,
            preset=args.preset,
            format=args.format,
            dpi=args.dpi,
            return_report=True,
        )
        print(
            f"Success: {report.pixel_width}x{report.pixel_height}px "
            f"{report.format.upper()} @ {report.dpi} DPI "
            f"({report.file_size_bytes:,} bytes) in {report.render_time_ms:.1f}ms"
        )
        print(f"Output: {out_path}")
    except Exception as exc:
        print(f"Error during compilation: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
