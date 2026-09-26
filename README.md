# cad-ir-to-raster: High-Fidelity Raster Image Compiler (PNG, JPEG, WebP)

<div align="center">

[![Python: 3.12+](https://img.shields.io/badge/Python-3.12+-3776AB.svg?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Formats: PNG/JPG/WebP](https://img.shields.io/badge/Formats-PNG%20%7C%20JPEG%20%7C%20WebP-54A0FF.svg?style=for-the-badge)](#)
[![Domain: AI Vision / CV](https://img.shields.io/badge/Domain-Multimodal%20AI%20%7C%20Computer%20Vision-5F27CD.svg?style=for-the-badge)](#)
[![Validation Suite](https://img.shields.io/badge/Test%20Suite-100%25%20Passing-2ED573.svg?style=for-the-badge)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

**A high-performance bitmap rendering engine translating canonical `LAVINCI_CAD_IR_V3` JSON models into anti-aliased PNG, JPEG, and WebP raster images, featuring auto-fit tight cropping, 8px linework buffer protection, and adaptive DPI stroke scaling.**

*Part of the **La Vinci** engineering initiative by **Saikat Dutta Chowdhury** (Mechanical Engineering).*

</div>

---

## 💡 The AI Vision & Computer Vision Challenge

Modern engineering and architecture workflows increasingly rely on **Multimodal AI Vision models (GPT-4V, Claude 3.5 Sonnet, Gemini 1.5 Pro)** to automate building code reviews, room classification, and drawing dimension verification.

However, standard CAD rasterization pipelines create severe obstacles for Computer Vision:
1. **Massive Empty Margins**: Coordinates placed far from the origin create vast empty letterboxing where the actual building renders as an indistinguishable speck.
2. **Perimeter Line Shearing**: Naive tight-crop algorithms chop off the anti-aliased outer edge of perimeter walls and vehicle chassis frames.
3. **High-DPI Line Fading**: Increasing resolution to 300 DPI without stroke scaling makes lines paper-thin and unreadable for optical recognition.

**`cad-ir-to-raster`** delivers pixel-perfect, anti-aliased raster outputs tailored for Computer Vision and high-speed web feeds:
* Driven by a headless **PyMuPDF + Pillow** rendering pipeline.
* **Auto-Fit Tight Cropping** that calculates the exact bounding box of non-background linework.
* Enforces an **8-pixel minimum boundary buffer invariant** to prevent edge-clipping.
* **Adaptive DPI stroke scaling** maintaining constant visual line presence across 72 to 1200 DPI.
* Multi-format encoding: Lossless PNG, Lightweight JPEG, and ultra-compact modern WebP.

```
[ Input: LAVINCI_CAD_IR_V3 JSON ]
               │
               ▼
┌──────────────────────────────────────────────┐
│         cad-ir-to-raster Pipeline            │
│                                              │
│  1. Layer Whitelist Filtering (Optional)     │
│     • Isolate specific engineering layers    │
│                                              │
│  2. Adaptive DPI Scaling (72 to 1200 DPI)    │
│     • Stroke scale = DPI / 150.0             │
│                                              │
│  3. PyMuPDF Pixmap Rasterization             │
│     • Sub-pixel anti-aliasing                │
│                                              │
│  4. Auto-Fit Tight Crop (8px Buffer)         │
│     • Image difference masking               │
│     • margin_px = max(margin_px, 8)          │
│                                              │
│  5. Multi-Format Encoding                    │
│     • PNG (Lossless)                         │
│     • JPEG (Standard)                        │
│     • WebP (VP8 Ultra-Compact, <20 KB)       │
└──────────────────────────────────────────────┘
               │
               ▼
[ Output: vision_ready.png / preview.webp ]
```

---

## 🔬 Mathematical Invariants & Crop Algorithms

### 1. Non-Background Pixel Bounding Envelope
To eliminate origin-offset letterboxing without losing drawing context, the engine generates an image difference mask between rendered pixels and background canvas $\vec{C}_{\text{bg}}$:
$$\Delta(x, y) = \|\vec{I}(x, y) - \vec{C}_{\text{bg}}\|_1$$
Extracts the tightest enclosing rectangle of active pixels:
$$X_{\min} = \min \{x \mid \Delta(x, y) > \epsilon\}, \quad X_{\max} = \max \{x \mid \Delta(x, y) > \epsilon\}$$
$$Y_{\min} = \min \{y \mid \Delta(x, y) > \epsilon\}, \quad Y_{\max} = \max \{y \mid \Delta(x, y) > \epsilon\}$$

### 2. The 8-Pixel Boundary Protection Invariant
Standard crop algorithms slice directly along non-zero pixels, cutting off the outer anti-aliased gradient of perimeter linework. `cad-ir-to-raster` strictly enforces:
```python
margin_px = int(max(crop_w, crop_h) * tight_crop_margin_percent)
# INVARIANT: Must be at least 8px to protect anti-aliased linework from edge shearing
margin_px = max(margin_px, 8)
```

### 3. Adaptive Linework Stroke Scaling
Guarantees identical visual linework weight across resolutions:
$$\text{EffectiveLineWidth} = \text{BaseLineWidth} \times \left(\frac{\text{DPI}}{150.0}\right)$$

---

## ⚡ Quick Start

### Installation
```bash
pip install -e products/cad-ir-to-raster
```

### Python SDK
```python
from cad_ir_to_raster import compile_ir_to_raster

# 1. Compile 300 DPI high-contrast PNG for AI Vision
compile_ir_to_raster(
    ir_source="structural_layout_ir.json",
    output_path="ai_vision_input.png",
    preset="ai-vision",
    dpi=300,
    tight_crop=True
)

# 2. Compile lightweight WebP thumbnail (<20 KB for mobile apps)
compile_ir_to_raster(
    ir_source="structural_layout_ir.json",
    output_path="thumb.webp",
    format="webp",
    dpi=72
)

# 3. Isolate specific layers (e.g. Walls and Columns only)
compile_ir_to_raster(
    ir_source="structural_layout_ir.json",
    output_path="structural_only.png",
    layers=["WALLS", "COLUMNS"],
    preset="architectural-monochrome"
)
```

### Command Line Interface (CLI)
```bash
# Render to standard PNG preview
python -m cad_ir_to_raster.cli drawing_ir.json -o output.png

# Render to 300 DPI AI Vision format
python -m cad_ir_to_raster.cli drawing_ir.json -o vision.png --preset ai-vision

# Render to modern WebP
python -m cad_ir_to_raster.cli drawing_ir.json -o preview.webp --format webp --dpi 150
```

---

## 📄 License

Licensed under the [MIT License](LICENSE).
