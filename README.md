# cad-ir-to-raster

**Product 5 of the [La Vinci / Rine](https://rine.studio) CAD processing ecosystem.**

High-fidelity raster image compiler that converts `LAVINCI_CAD_IR_V3` CAD Intermediate Representations into pixel-perfect **PNG**, **JPEG**, and **WebP** images. Headless, cloud-ready, and zero mandatory disk I/O.

```
AutoCAD DWG / DXF → cad-extractor-ir → LAVINCI_CAD_IR_V3 → cad-ir-to-raster → PNG / JPEG / WebP
```

---

## Features

- **One clean API**: `compile_ir_to_raster(ir_source, output_path=None, preset=..., format=..., dpi=...)`
- **Three output formats**: PNG (lossless, crisp lines), JPEG (compressed), WebP (modern web delivery)
- **Preset system**: Start with `web-preview` (150 DPI PNG). Add presets for thumbnails, AI vision, dark mode, archival print — all via config.
- **100% in-memory / headless**: Returns `bytes` when `output_path=None`. Zero disk writes required. Runs in AWS Lambda, FastAPI, Docker containers.
- **Adversarial hardened**: NaN/Inf coordinates, empty drawings, degenerate geometry, malformed metadata — all handled gracefully.
- **Telemetry**: Optional `RasterReport` with pixel dimensions, file size, render time, entity counts.

---

## Installation

```bash
# From the La Vinci workspace root:
pip install -e products/cad-ir-to-svg    # Required dependency
pip install -e products/cad-ir-to-raster
```

---

## Quick Start

### Python API

```python
from cad_ir_to_raster import compile_ir_to_raster
import json

# Load a LAVINCI_CAD_IR_V3 payload
with open("drawing.json", "r") as f:
    ir = json.load(f)

# 1. Save to file (default: PNG @ 150 DPI)
output_path = compile_ir_to_raster(ir, output_path="preview.png")

# 2. Get raw bytes in-memory (headless / Lambda mode)
png_bytes = compile_ir_to_raster(ir)

# 3. JPEG at 300 DPI
jpeg_bytes = compile_ir_to_raster(ir, format="jpeg", dpi=300)

# 4. WebP with full telemetry report
webp_bytes, report = compile_ir_to_raster(ir, format="webp", return_report=True)
print(f"{report.pixel_width}x{report.pixel_height}px in {report.render_time_ms:.1f}ms")

# 5. Preset by name
png_bytes = compile_ir_to_raster(ir, preset="ai-vision")  # 300 DPI PNG

# 6. Custom preset
from cad_ir_to_raster import RasterPreset
my_preset = RasterPreset(name="custom", format="png", dpi=72, max_dimension=512)
thumb = compile_ir_to_raster(ir, preset=my_preset)
```

### CLI

```bash
cad-ir-to-raster drawing.json -o preview.png
cad-ir-to-raster drawing.json -o preview.jpg --format jpeg --dpi 300
cad-ir-to-raster drawing.json -o thumb.webp --preset web-thumbnail
```

---

## Preset Reference

| Preset | Format | DPI | Background | Use Case |
|---|---|---|---|---|
| `web-preview` *(default)* | PNG | 150 | White | Web dashboards, client previews |
| `web-thumbnail` | WebP | 72 | White | File browser thumbnails (max 512px) |
| `ai-vision` | PNG | 300 | White | Multimodal LLM / AI vision model input |
| `cad-dark-modelspace` | PNG | 150 | `#1E1E1E` | Authentic AutoCAD dark canvas look |
| `architectural-monochrome` | PNG | 300 | White | Blueprint documentation & print |

Custom presets: construct `RasterPreset(name=..., format=..., dpi=..., ...)` and pass directly.

---

## Architecture

```
compile_ir_to_raster(ir_source)
    │
    ├─ Step 1: Load IR (dict / file path / JSON string / Pydantic model)
    │
    ├─ Step 2: Compile IR → SVG string in-memory
    │          (via cad-ir-to-svg: Y-inversion, contrast safety, block unrolling)
    │
    ├─ Step 3: Rasterize SVG → PyMuPDF Pixmap @ target DPI
    │
    ├─ Step 4: Apply max_dimension cap (proportional Lanczos downscale via Pillow)
    │
    └─ Step 5: Encode → PNG (PyMuPDF native) / JPEG (PyMuPDF native) / WebP (Pillow)
               Return bytes or write to file
```

---

## GOLDEN_RULES.md Compliance

- Zero intermediate format hops beyond the single SVG rendering stage.
- All operations are headless and stateless (AWS Lambda / ECS ready).
- Full automated test suite (36 tests) must pass before any commit.
- Semantic commits pushed immediately to `origin/main`.
