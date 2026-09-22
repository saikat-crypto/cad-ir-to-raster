# cad-ir-to-raster: High-Fidelity Raster Image Compiler (PNG, JPEG, WebP)

> **Product**: `cad-ir-to-raster`  
> **Package Version**: `1.0.0`  
> **Source Directory**: `products/cad-ir-to-raster/`  
> **Role in Ecosystem**: Raster Egress Compiler (`LAVINCI_CAD_IR_V3` $\to$ PNG / JPEG / WebP)  

---

## 1. Executive Summary & Architectural Scope

The **`cad-ir-to-raster`** compiler transforms canonical **`LAVINCI_CAD_IR_V3`** JSON representations into pixel-perfect, anti-aliased bitmap images in **PNG**, **JPEG**, and **WebP** formats.

While vector formats (PDF, SVG) are ideal for interactive drafting and plotting, web platforms, mobile thumbnails, social sharing, and **Multimodal AI Vision models (GPT-4V, Claude 3.5 Sonnet, Gemini 1.5 Pro)** require standardized, high-contrast raster representations:
* **Sub-Pixel Anti-Aliased Rendering**: Driven by a headless PyMuPDF + Pillow rendering pipeline that avoids common grid-discretization artifacts.
* **Auto-Fit & Tight-Crop Engine**: Eliminates massive letterboxing caused by origin offsets and drawing stamps, cropping tightly around the active geometry.
* **Tight-Crop Buffer Protection**: Enforces an 8-pixel minimum boundary buffer, ensuring anti-aliased perimeter linework is never sheared at canvas borders.
* **Multi-Format Compression Matrix**: Generates lossless PNGs for technical analysis, lightweight JPEGs for fast previews, and ultra-compressed WebPs (up to 65% smaller than PNG) for mobile web delivery.

```
 ┌──────────────────────────────┐
 │   LAVINCI_CAD_IR_V3 (JSON)   │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │  Layer Whitelist Filtering   │
 │   - Optional layer subset    │
 │     e.g. ['WALLS', 'DOORS']  │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │ Intermediate Vector Synthesis│
 │   - Native contrast colors   │
 │   - Proportional stroke width│
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │ PyMuPDF Pixmap Rasterization │
 │   - Target DPI (72 to 1200)  │
 │   - Alpha blending & fills   │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │  Auto-Fit & Tight-Crop Pass  │
 │   - Non-background pixel bbox│
 │   - margin_px >= 8px buffer  │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │ Max Dimension Downscaling    │
 │   - Lanczos anti-aliasing    │
 └──────────────┬───────────────┘
                │
                ▼
 ┌──────────────────────────────┐
 │ Format Encoder (PNG/JPG/WEBP)│
 └──────────────────────────────┘
```

---

## 2. Mathematical Pipeline: DPI Scaling & Anti-Aliased Rasterization

### 2.1 Resolution & DPI Mathematics
The target canvas resolution in pixels is a function of the drawing extent dimensions (in inches or normalized units) and the requested dots-per-inch ($\text{DPI}$):

$$\text{Scale}_{\text{dpi}} = \frac{\text{DPI}}{72.0}$$
$$\text{Width}_{\text{px}} = \lceil W_{\text{units}} \times \text{Scale}_{\text{dpi}} \rceil$$
$$\text{Height}_{\text{px}} = \lceil H_{\text{units}} \times \text{Scale}_{\text{dpi}} \rceil$$

### 2.2 Adaptive Linework Stroke Scaling
If line thickness remained constant while increasing DPI, high-resolution 300 DPI images would render lines that appear paper-thin and visually faint.

`cad-ir-to-raster` scales stroke widths adaptively with resolution:

$$\text{StrokeScale} = \frac{\text{DPI}}{150.0}$$
$$\text{EffectiveLineWidth} = \text{BaseLineWidth} \times \text{StrokeScale}$$

This ensures that linework maintains identical visual presence whether rendered at 72 DPI for a mobile card or 600 DPI for archival printing.

---

## 3. The Auto-Fit & Tight-Crop Engine

CAD drawings are notorious for having vast empty spaces between the model origin $(0, 0)$ and the actual building coordinates. Without cropping, a $100\text{m}$ building placed at coordinate $(50000, 50000)$ renders as a tiny, indistinguishable dot surrounded by massive white letterboxing.

### 3.1 Non-Background Pixel Bounding Box Extraction
`cad-ir-to-raster` computes the tightest bounding box of actual non-background linework pixels:
1. Converts the canvas background hex string (e.g. `#FFFFFF` or dark mode `#1E1E1E`) into an RGB tuple:
   $$\vec{C}_{\text{bg}} = (R_{\text{bg}}, G_{\text{bg}}, B_{\text{bg}})$$
2. Creates an image difference mask between the rendered pixmap and a solid background canvas:
   $$\Delta(x, y) = |\vec{I}(x, y) - \vec{C}_{\text{bg}}|$$
3. Identifies the bounding envelope:
   $$X_{\text{crop\_min}} = \min \{x \mid \Delta(x, y) > \epsilon\}, \quad X_{\text{crop\_max}} = \max \{x \mid \Delta(x, y) > \epsilon\}$$
   $$Y_{\text{crop\_min}} = \min \{y \mid \Delta(x, y) > \epsilon\}, \quad Y_{\text{crop\_max}} = \max \{y \mid \Delta(x, y) > \epsilon\}$$

---

### 3.2 The 8-Pixel Boundary Protection Invariant
During our empirical audit, we observed that aggressive cropping chopped off the outer anti-aliased gradient of perimeter lines (e.g. the outer frame of a car chassis or the edge of a wall).

`cad-ir-to-raster` enforces a strict minimum margin buffer:
```python
# Calculate margin as 3% of the larger dimension
margin_px = int(max(crop_w, crop_h) * preset.tight_crop_margin_percent)

# INVARIANT: Must be at least 8px to protect anti-aliased linework from edge shearing
margin_px = max(margin_px, 8)

crop_box = (
    max(0, X_min - margin_px),
    max(0, Y_min - margin_px),
    min(orig_w, X_max + margin_px),
    min(orig_h, Y_max + margin_px),
)
```

---

## 4. Presets and Options Configuration

### 4.1 Production Preset Catalog

| Preset Name | Target Format | Resolution (DPI) | Canvas Background | Cropping Mode | Best Use Case |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **`web-preview`** *(Default)* | PNG | 150 DPI | `#FFFFFF` | Standard Padding | High-quality web viewing, general documentation. |
| **`cad-dark-modelspace`** | PNG | 150 DPI | `#1E1E1E` | Auto-Fit Crop | Authentic AutoCAD ModelSpace experience for developers. |
| **`web-thumbnail`** | JPEG | 72 DPI | `#FFFFFF` | Max Dim (300px) | Ultra-fast gallery cards, mobile listing feeds. |
| **`ai-vision`** | PNG | 300 DPI | `#FFFFFF` | Tight Crop (8px) | High-contrast ingestion for Multimodal LLM Vision models. |
| **`architectural-monochrome`** | PNG | 200 DPI | `#FFFFFF` | Tight Crop | Clean black linework on pure white for technical reports. |

---

### 4.2 Runtime Surgical Overrides

In addition to presets, `compile_ir_to_raster()` accepts direct surgical argument overrides:
* `format`: Override the output encoding (`"png"`, `"jpeg"`, `"webp"`).
* `dpi`: Override resolution ($1 \le \text{DPI} \le 1200$).
* `tight_crop`: Force enable (`True`) or disable (`False`) the auto-fit cropping engine.
* `background_color`: Force canvas background (e.g. `"#002040"` for blueprints, `"transparent"` for alpha PNGs).
* `layers`: Whitelist of layer names to render (case-insensitive). All unlisted layers are omitted.

---

## 5. Public API & Usage Reference

### 5.1 Python SDK

```python
from cad_ir_to_raster import compile_ir_to_raster

# 1. Standard Web Preview (Returns raw PNG bytes in headless mode)
png_bytes = compile_ir_to_raster(
    ir_source="ir_data.json",
    output_path=None,           # Headless API mode
    preset="web-preview"
)

# 2. High-Res 300 DPI Print to Disk
compile_ir_to_raster(
    ir_source=ir_dict,
    output_path="floorplan_300dpi.png",
    preset="web-preview",
    dpi=300,
    tight_crop=True
)

# 3. Modern Ultra-Compressed WebP Export
webp_bytes = compile_ir_to_raster(
    ir_source=ir_dict,
    output_path="preview.webp",
    format="webp",
    dpi=200
)

# 4. Surgical Layer Isolation (Render Walls & Doors only)
walls_only_bytes = compile_ir_to_raster(
    ir_source=ir_dict,
    output_path=None,
    layers=["A-WALL", "A-DOOR"],
    preset="architectural-monochrome"
)
```

---

### 5.2 Command Line Interface (CLI)

```bash
# Render to standard PNG preview
python -m cad_ir_to_raster.cli input_ir.json -o output.png

# Render to 300 DPI AI Vision format
python -m cad_ir_to_raster.cli input_ir.json -o vision_300dpi.png --preset ai-vision

# Render to WebP with custom dark background
python -m cad_ir_to_raster.cli input_ir.json -o dark.webp \
       --format webp \
       --dpi 200 \
       --background-color "#1E1E1E"

# Isolate structural layers only
python -m cad_ir_to_raster.cli input_ir.json -o structure.png --layers "WALLS,COLUMNS"
```

---

## 6. Output Format Comparison & Selection Guide

| Dimension | PNG | JPEG | WebP |
| :--- | :--- | :--- | :--- |
| **Compression** | Lossless (Deflate) | Lossy (DCT) | Lossy & Lossless (VP8) |
| **Alpha Transparency** | Full 8-bit Alpha Channel | None (Solid background required) | Full 8-bit Alpha Channel |
| **Relative File Size** | 100% (Baseline) | ~30% – 50% of PNG | **~15% – 35% of PNG** (Smallest) |
| **Artifacts** | Zero (Crisp vectors) | Minor ringing around high-frequency lines | Negligible ringing |
| **Recommended Use** | Archival, CAD inspections, AI OCR | Thumbnails, gallery previews | Mobile apps, modern web apps |
