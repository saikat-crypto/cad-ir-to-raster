# Technical Handoff: `cad-ir-to-raster` (Product 5)

**Module**: `cad-ir-to-raster`  
**Namespace**: `cad_ir_to_raster`  
**Repository**: `saikat-crypto/cad-ir-to-raster`  
**Standard**: `LAVINCI_CAD_IR_V3`  
**Pipeline Role**: Pure In-Memory Rasterization Engine (IR $\to$ Vector SVG $\to$ High-Fidelity Raster Image)

---

## 1. Architectural Overview & Design Philosophy

`cad-ir-to-raster` is the 5th product in the La Vinci CAD compiler suite. It transforms `LAVINCI_CAD_IR_V3` intermediate representation payloads into web-optimized, AI-ready, or publication-grade raster images (PNG, JPEG, WebP).

```
┌─────────────────────────┐
│   LAVINCI_CAD_IR_V3     │ (dict, JSON string, or Path)
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│     cad-ir-to-svg       │ (In-memory SVG vector generation)
│  - Contrast remapping   │ (WCAG 2.1 AA luminance safety)
│  - Adaptive stroke      │ (Proportional stroke scaling for high DPI)
└───────────┬─────────────┘
            │ SVG XML bytes
            ▼
┌─────────────────────────┐
│      PyMuPDF Engine     │ (Native C rasterizer: zero browser overhead)
│  - Sub-pixel anti-alias │
│  - DPI resolution scale │
└───────────┬─────────────┘
            │ Raw Pixmap
            ▼
┌─────────────────────────┐
│  Tight-Crop / Auto-Fit  │ (Pillow ImageChops background difference)
│  - Eliminates whitespace│ (Dark & light canvas boundary aware)
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  Max Dimension Cap &    │ (Lanczos proportional downsampling)
│     Container Encode    │ (PNG / JPEG / WebP)
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  bytes OR file on disk  │ + RasterReport telemetry
└─────────────────────────┘
```

### Key Engineering Guarantees
1. **Zero Mandatory Disk I/O**: Operates 100% in-memory via byte streams. Zero temporary files on disk. Suitable for AWS Lambda, Google Cloud Functions, FastAPI workers, and MCP server tools.
2. **Deterministic & Headless**: No headless Chrome/Playwright, no X11/display server, no external daemon or subprocesses. Pure native Python C-extension bindings (`pymupdf` + `Pillow`).
3. **Fail-Fast Developer Experience (DX)**: Custom exception hierarchy inheriting from `ValueError` for full standard-library compatibility, providing exact bad inputs, valid ranges, and "Did you mean?" suggestions.
4. **Adaptive Contrast & Legibility**: Prevents cyan/yellow linework from washing out against white paper or dark canvases using WCAG 2.1 luminance calculation. Scales stroke weights proportionally at high DPI so fine engineering details remain visible to multimodal AI vision models (GPT-4o, Claude 3.5 Sonnet, Gemini 1.5 Pro).

---

## 2. Module Ingestion: Input Schemas & Accepted Types

### Public Entrypoint
```python
from cad_ir_to_raster import compile_ir_to_raster

def compile_ir_to_raster(
    ir_source: Union[str, Path, Dict[str, Any], Any],
    output_path: Optional[Union[str, Path]] = None,
    preset: Optional[Union[RasterPreset, str]] = None,
    format: Optional[str] = None,
    dpi: Optional[int] = None,
    tight_crop: Optional[bool] = None,
    background_color: Optional[str] = None,
    layers: Optional[List[str]] = None,
    return_report: bool = False,
) -> Union[Path, bytes, Tuple[Union[Path, bytes], RasterReport]]:
```

### Accepted `ir_source` Types
The module normalizes `ir_source` in `_load_ir_dict`:
1. **`dict`**: Direct parsed dictionary matching `LAVINCI_CAD_IR_V3`.
2. **`pathlib.Path`**: Filepath pointing to an existing JSON file on disk.
3. **`str` (Filepath)**: Valid file path string pointing to an existing JSON file.
4. **`str` (JSON String)**: Raw serialized JSON string starting with `{` and ending with `}`.
5. **Pydantic Model**: Any object exposing `.model_dump()` or `.dict()`.

### Expected `LAVINCI_CAD_IR_V3` Schema Top-Level Keys
```json
{
  "format": "LAVINCI_CAD_IR_V3",
  "metadata": {
    "source_file": "drawing.dwg",
    "has_proxy_entities": false
  },
  "extents": {
    "min": [0.0, 0.0],
    "max": [100.0, 100.0],
    "width": 100.0,
    "height": 100.0
  },
  "layers": [
    {
      "name": "WALLS",
      "color_aci": 7,
      "hex_color": "#000000"
    }
  ],
  "geometry_primitives": {
    "primitives": {
      "lines": [],
      "arcs": [],
      "circles": [],
      "polylines": []
    }
  },
  "components": [],
  "annotations": [],
  "dimensions": []
}
```

*Note: Missing geometry keys or empty primitives do not crash the engine; they render as clean, empty canvases.*

---

## 3. Output Schema & Return Types

Depending on `output_path` and `return_report`:

| `output_path` | `return_report` | Return Type | Description |
|---|---|---|---|
| `None` (Default) | `False` (Default) | `bytes` | Raw encoded image bytes (PNG, JPEG, or WebP). |
| `None` | `True` | `Tuple[bytes, RasterReport]` | In-memory bytes + telemetry dataclass. |
| `"/path/out.png"` | `False` | `pathlib.Path` | Resolved path of the written file. |
| `"/path/out.png"` | `True` | `Tuple[pathlib.Path, RasterReport]` | Resolved path + telemetry dataclass. |

### `RasterReport` Telemetry Schema (`telemetry.py`)
```python
@dataclass
class RasterReport:
    output_target: str = "<in-memory>"      # Filepath or "<in-memory>"
    success: bool = False                   # True if rasterization succeeded
    preset_name: str = "web-preview"        # Active preset name
    format: str = "png"                     # Normalized format ("png", "jpeg", "webp")
    dpi: int = 150                          # Final DPI rendered
    pixel_width: int = 0                    # Output image width in pixels
    pixel_height: int = 0                   # Output image height in pixels
    file_size_bytes: int = 0                # Final image size in bytes
    total_entities_read: int = 0            # Total entities parsed from IR
    total_entities_rendered: int = 0        # Entities successfully rendered in SVG
    total_entities_dropped: int = 0         # Outliers or degenerate primitives pruned
    cad_bbox_extents: Dict[str, float] = field(default_factory=dict) # min_x, min_y, max_x, max_y, width, height
    tight_crop_applied: bool = False        # True if auto-fit whitespace trimming was applied
    render_time_ms: float = 0.0             # End-to-end latency in milliseconds
    warnings: List[str] = field(default_factory=list) # Non-fatal diagnostic warnings
    error: Optional[str] = None             # Error string if failure occurred
```

---

## 4. Preset Catalog & Granular Knobs

### The 5 Curated Safe Presets (`config.py`)

| Preset Name | Container | DPI | Background | Color Mode | Max Dim | Tight-Crop | Primary Intended Use Case |
|---|---|:---:|:---:|:---:|:---:|:---:|---|
| **`web-preview`** *(Default)* | PNG | 150 | `#FFFFFF` | Contrast-Safe | None | True (3%) | General web viewing, SaaS dashboards, default previews. |
| **`web-thumbnail`** | WebP | 72 | `#FFFFFF` | Contrast-Safe | 512 px | True (2%) | Micro-thumbnails, file pickers, mobile previews. Minimal bandwidth. |
| **`ai-vision`** | PNG | 300 | `#FFFFFF` | Contrast-Safe | None | True (2%) | Multi-modal LLM inspection (GPT-4o, Claude 3.5, Gemini). Adaptive line weights. |
| **`cad-dark-modelspace`** | PNG | 150 | `#1E1E1E` | Native ACI | None | True (3%) | Traditional AutoCAD modelspace look. High-contrast neon vectors. |
| **`architectural-monochrome`** | PNG | 300 | `#FFFFFF` | Monochrome | None | True (2%) | Construction prints, permit submissions, patent illustrations. Pure black linework. |

### The 5 Advanced Overrides ("Knobs")

Every per-call parameter overrides the active preset's setting for that specific invocation:

1. **`format: Optional[str]`**:
   - Supported: `"png"`, `"jpeg"` (or `"jpg"`), `"webp"`.
   - Normalization: `"jpg"` automatically maps to canonical `"jpeg"`.
2. **`dpi: Optional[int]`**:
   - Allowed range: `1` to `1200`.
   - Presets default to `72`, `150`, or `300`.
3. **`tight_crop: Optional[bool]`**:
   - `True`: Scans rendered pixel arrays for actual linework, cropping dead coordinate margins and letterboxing.
   - `False`: Renders full uncropped extents including drawing border sheets.
4. **`background_color: Optional[str]`**:
   - Accepts 6-character hex strings (e.g., `"#FFFFFF"`, `"#0A2540"`, `"#1E1E1E"`).
   - Accepts `"transparent"` (PNG only, alpha channel preserved; transparent SVG generation).
5. **`layers: Optional[List[str]]`**:
   - Whitelist of layer names to render (case-insensitive, e.g., `layers=["WALLS", "DOORS"]`).
   - `None` (default): Renders all active drawing layers.

---

## 5. Validation Rules & Custom Error Hierarchy

All custom exceptions inherit from `CadRasterError`, which subclasses Python's standard `ValueError`. Callers can catch `CadRasterError` specifically, or rely on standard `except ValueError:` handling.

```
Exception
 └── ValueError
      └── CadRasterError (Base)
           ├── InvalidPresetError
           ├── InvalidFormatError
           ├── InvalidDpiError
           ├── InvalidColorError
           ├── InvalidIrPayloadError
           └── InvalidLayerError
```

### Exception Specification & Failure Modes

| Exception | Condition | Developer Message / Suggestion |
|---|---|---|
| **`InvalidPresetError`** | Preset name not in registry. | Lists valid presets and runs fuzzy matching (e.g., `web_preview` $\to$ *"Did you mean 'web-preview'?"*). |
| **`InvalidFormatError`** | Format not in `('png', 'jpeg', 'jpg', 'webp')`. | Lists supported formats: `['png', 'jpeg', 'webp']`. |
| **`InvalidDpiError`** | `dpi < 1` or `dpi > 1200`. | Informs valid bounds `[1, 1200]` and provides recommended values (`72`, `150`, `300`). |
| **`InvalidColorError`** | Color string is not a valid `#RRGGBB` hex or `"transparent"`. | Details required hex format with examples (`'#FFFFFF'`, `'#0A2540'`). |
| **`InvalidIrPayloadError`** | Target is `None`, non-existent path, or invalid JSON. | Explains allowed input types (`dict`, file path, JSON string). |
| **`InvalidLayerError`** | `layers` parameter is not a `List[str]`. | Explains required type `list of str` and provides usage example. |

---

## 6. Diagnostic Warnings & Telemetry Logging

Non-fatal anomalies do not raise exceptions; they append structured warning strings to `RasterReport.warnings`:

1. **Autodesk ObjectARX Proxy Entities**:
   - Trigger: Drawing contains `AECPROXYGRAPHICS` or Civil 3D custom objects.
   - Message: *"Drawing contains Autodesk ObjectARX proxy entities (AECPROXYGRAPHICS/Civil 3D). Custom geometric objects require upstream flattening for full vector fidelity."*
2. **Active Layer Filter Telemetry**:
   - Trigger: `layers=["WALLS"]` passed to compile call.
   - Message: *"Layer filter active — only rendering layers: ['WALLS']. Entities after filter: 1420."*
3. **Outlier Pruning Telemetry** (from `cad-ir-to-svg`):
   - Trigger: Scratch geometry or rogue coordinates detected far outside the main modelspace cluster.
   - Message: Logged in SVG compilation report, reflected in `report.total_entities_dropped`.

---

## 7. Supported vs. Unsupported CAD Entities

| Entity / Feature | Support Level | Engine Handling |
|---|:---:|---|
| **Lines / Arcs / Circles** | Full | Precise mathematical SVG paths; rendered via PyMuPDF anti-aliased engine. |
| **LWPolylines (Bulges & Segments)** | Full | Arc bulges calculated and unrolled to standard SVG arc commands. |
| **Dimensions (Linear & Aligned)** | Full | Dimension text, extension lines, and arrowheads preserved. |
| **Text & MText** | Full | Sanitized, Y-inverted, styled with standard sans-serif fallback fonts. |
| **Nested Blocks & Components** | Full | Flattened up to depth 16; insertion affine transforms applied. |
| **AutoCAD Color Index (ACI 1-255)**| Full | Mapped to RGB hex; luminance adjusted for light/dark canvas contrast safety. |
| **TrueColor (RGB)** | Full | Rendered directly with 24-bit color fidelity. |
| **ObjectARX 3D Solids / ACIS Bodies** | Partial (Upstream) | Requires 2D wireframe proxy graphics present in the DWG/IR. Emits telemetry warning. |
| **Paper Space Viewports** | Configurable | Defaults to `"Model"` space. Specific layout spaces accessible via preset configuration. |

---

## 8. Performance Characteristics & Benchmarks

Empirical performance measured on real-world industrial drawings (up to 26,000 entities, 4.6 MB IR):

| Workload | Input | Output Specs | Typical Latency | Peak Memory |
|---|---|---|:---:|:---:|
| **Standard Preview** | 2.5 MB DWG (26k entities) | 150 DPI PNG (855 × 546 px) | ~3.5 s | < 120 MB |
| **High-Res AI Vision** | 2.5 MB DWG (26k entities) | 300 DPI PNG (1660 × 1041 px) | ~3.8 s | < 180 MB |
| **Web Thumbnail** | 2.5 MB DWG (26k entities) | 72 DPI WebP (398 × 249 px) | ~3.4 s | < 90 MB |
| **Parallel Compilation** | 2.5 MB DWG (3 presets) | Concurrent PNG + WebP | ~4.8 s total | < 260 MB |

### Memory & Execution Invariants
- **Thread Safety**: The compiler is fully thread-safe. `compile_all_presets_parallel()` parses the IR dictionary once and shares read-only access across worker threads.
- **Garbage Collection**: PyMuPDF documents (`mupdf_doc`) and Pixmap buffers are closed immediately following conversion to byte streams.
- **Decompression Bomb Protection**: Pillow decompression limits are monitored; large high-DPI canvases automatically use max-dimension caps where configured.

---

## 9. Parallel Multi-Preset Compilation API

To generate previews, thumbnails, and AI vision assets simultaneously without redundant IR parsing:

```python
from cad_ir_to_raster import compile_all_presets_parallel

results = compile_all_presets_parallel(
    ir_source="path/to/drawing_ir.json",
    presets=["web-preview", "web-thumbnail", "ai-vision"],
    max_workers=3
)

# Output structure:
# {
#   "web-preview": (png_bytes, RasterReport),
#   "web-thumbnail": (webp_bytes, RasterReport),
#   "ai-vision": (png_bytes, RasterReport)
# }

preview_bytes, preview_report = results["web-preview"]
print(f"Rendered {preview_report.pixel_width}x{preview_report.pixel_height} in {preview_report.render_time_ms:.1f}ms")
```

---

## 10. Pre-Flight Size Introspection API

To inspect image dimensions before allocating full encoding buffers (useful for HTTP headers or layout planning):

```python
from cad_ir_to_raster import get_raster_dimensions

width, height = get_raster_dimensions(ir_dict, preset="web-preview", dpi=150)
print(f"Target dimensions: {width} x {height} px")
```

---

## 11. Code Examples

### Example 1: Headless API / AWS Lambda Handler (Zero Disk I/O)
```python
from cad_ir_to_raster import compile_ir_to_raster

def lambda_handler(event, context):
    ir_data = event["ir_json"]
    
    # Render in-memory PNG bytes
    image_bytes, report = compile_ir_to_raster(
        ir_data,
        preset="web-preview",
        return_report=True
    )
    
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "image/png",
            "X-Render-Time-Ms": str(report.render_time_ms),
            "X-Image-Dimensions": f"{report.pixel_width}x{report.pixel_height}"
        },
        "isBase64Encoded": True,
        "body": image_bytes.hex()
    }
```

### Example 2: Layer Filtering with Custom Blueprint Navy Canvas
```python
from cad_ir_to_raster import compile_ir_to_raster

# Render only structural walls and doors against blueprint navy
output_path = compile_ir_to_raster(
    "floorplan_ir.json",
    output_path="structural_walls.png",
    preset="architectural-monochrome",
    background_color="#0A2540",
    layers=["WALLS", "DOORS", "COLUMNS"]
)
print(f"Saved filtered raster to: {output_path}")
```

### Example 3: Safe Developer Exception Handling
```python
from cad_ir_to_raster import compile_ir_to_raster, CadRasterError, InvalidPresetError

try:
    image_bytes = compile_ir_to_raster(ir_payload, preset="web_preview")
except InvalidPresetError as e:
    # Captures actionable suggestion: "Did you mean 'web-preview'?"
    print(f"Preset error: {e}")
except CadRasterError as e:
    # Catches any other engine error
    print(f"Compilation failed: {e}")
```

---

## 12. External Dependencies & Runtime Environment

### Python Environment
- Python 3.10+ (Tested through Python 3.12).
- Native C extensions required:
  - `pymupdf >= 1.20.0` (MuPDF vector rendering engine)
  - `Pillow >= 9.0.0` (Image processing, WebP support, image chops)

### Inter-Package Dependencies in Ecosystem
- `cad-ir-to-svg`: Local sibling package in repo (`products/cad-ir-to-svg`).
  Must be installed in the environment: `pip install -e products/cad-ir-to-svg`.

### Native System Dependencies / Subprocesses
- **Subprocesses**: None.
- **Temp Directories**: None.
- **External Binaries**: None (all compiled C libraries are statically packaged within wheels for `pymupdf` and `Pillow`).

---

## 13. Integration Checklist for Downstream Wrapper Teams

When wrapping `cad-ir-to-raster` into an MCP tool, REST API, or worker queue:

- [ ] **Pass Dict or Path Directly**: Avoid repeated JSON serialization/deserialization. If you already have a dictionary, pass it straight into `compile_ir_to_raster(ir_dict)`.
- [ ] **Use Presets for Default Routes**: Map standard API endpoints directly to preset names (`"web-preview"`, `"web-thumbnail"`, `"ai-vision"`).
- [ ] **Leverage `return_report=True` for Telemetry**: Always record `render_time_ms`, `pixel_width`, and `warnings` into your API telemetry or OpenTelemetry spans.
- [ ] **Forward ObjectARX Warnings**: If `report.warnings` contains an ObjectARX warning, forward this to the API consumer so they understand potential missing 3D proxy solids.
- [ ] **Handle `CadRasterError` as HTTP 400**: Custom exceptions indicate caller input errors (invalid format, invalid DPI, unknown preset). Map `CadRasterError` directly to HTTP 400 Bad Request with the exception's message in the JSON error response body.
