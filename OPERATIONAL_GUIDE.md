# La Vinci Operational Field Manual: Safe Usage, Industrial Use Cases, Deep Edge Cases & Troubleshooting Guide

> **Document Classification**: Master Production & Engineering Manual  
> **Applicable Standard**: `LAVINCI_CAD_IR_V3` / Cloud API v1.0  
> **Target Audience**: Systems Architects, Lead Engineers, CAD Automation Specialists, DevOps & Security Teams  
> **Status**: Production Verified & Hardened  

---

## 1. Executive Summary & Operational Invariants

AutoCAD `.dwg`, `.dxf`, and `.dwt` files represent over four decades of computational geometry legacy. Across architectural, engineering, construction (AEC), and manufacturing domains, CAD drawings vary wildly—from micro-machined watch gears measuring $0.05\text{ mm}$ to municipal infrastructure plans spanning $100\text{ km}$ in state plane coordinates.

Processing these files safely in a serverless, cloud-native API without memory exhaustion, thread deadlocks, or visual degradation requires strict observance of system invariants.

### 1.1 The Golden Operating Invariants

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          SYSTEM OPERATIONAL BOUNDS                          │
├───────────────────────────────┬─────────────────────────────────────────────┤
│ Dimension                     │ Operational Ceiling / Safe Threshold        │
├───────────────────────────────┼─────────────────────────────────────────────┤
│ Maximum Upload Payload        │ 30.0 MB (Multipart CAD binary stream)       │
├───────────────────────────────┼─────────────────────────────────────────────┤
│ Maximum Primitives per File   │ 500,000 geometric entities                  │
├───────────────────────────────┼─────────────────────────────────────────────┤
│ Max Coordinate Dynamic Range  │ |X|, |Y| ≤ 1.0 × 10^9 drawing units         │
├───────────────────────────────┼─────────────────────────────────────────────┤
│ Outlier Pruning Trigger       │ Inter-cluster coordinate gap > 5× median    │
├───────────────────────────────┼─────────────────────────────────────────────┤
│ Block Nesting Recursion Limit │ 16 levels maximum depth                     │
├───────────────────────────────┼─────────────────────────────────────────────┤
│ Memory Provisioning (Lambda)  │ 2,048 MB RAM (Allocates ~1.8 vCPU compute)  │
├───────────────────────────────┼─────────────────────────────────────────────┤
│ Maximum Lambda Timeout        │ 60 seconds (Auto-abort to prevent runaway)  │
├───────────────────────────────┼─────────────────────────────────────────────┤
│ Client-Side Recommended Timeout│ 45 to 60 seconds (Accounts for cold-starts) │
├───────────────────────────────┼─────────────────────────────────────────────┤
│ Safe Raster DPI Range         │ 72 DPI (Thumbnail) to 600 DPI (Archival)   │
├───────────────────────────────┼─────────────────────────────────────────────┤
│ Tight-Crop Buffer Invariant   │ margin_px = max(margin_px, 8)               │
└───────────────────────────────┴─────────────────────────────────────────────┘
```

---

### 1.2 Architectural Separation of Concerns: Ingestion vs Compilation

Clients interacting with the La Vinci API must choose between two distinct integration patterns depending on throughput and caching requirements:

```
Pattern A: One-Shot Unified Conversion
Client ────────► POST /convert (Multipart DWG) ────────► Output (PDF / SVG / PNG)
[Best for: Single document conversions, mobile uploads, direct downloads]

Pattern B: Decoupled Extraction & Multi-Format Fan-Out
Client ────────► POST /extract (Multipart DWG) ────────► Store LAVINCI_CAD_IR_V3 JSON
                                                                   │
               ┌───────────────────┬───────────────────────────────┴──────────┐
               ▼                   ▼                                          ▼
       POST /convert       POST /convert                              POST /convert
     (target: PDF A1)    (target: SVG Light)                        (target: PNG 300DPI)
[Best for: Asset processing pipelines, multi-resolution generation, caching layer]
```

---

## 2. Industrial Production Use Cases & Preset Blueprints

Below are end-to-end recipes for the primary production workflows supported by La Vinci across manufacturing, AEC, GIS, and web platforms.

---

### 2.1 Use Case 1: Interactive Web CAD & BIM Viewers (React / Vue / Three.js)
* **Goal**: Deliver zero-footprint vector floorplans inside web browsers with pan, zoom, and dynamic layer selection without requiring desktop CAD plugins.
* **Target Format**: `SVG`
* **Optimal Preset**: `web-interactive-light`
* **Architectural Mechanics**:
  - Emits semantic layer tags: `<g id="layer-{name}" class="cad-layer" data-layer-name="{name}">`.
  - Injects `vector-effect="non-scaling-stroke"` so lines stay crisp and constant-width during mouse-wheel zooming.
  - Dynamically calculates stroke widths via bounding-box diagonal scaling to prevent ink-bleeding.

#### Production cURL Implementation
```bash
curl -X POST "https://lavinci.rine.studio/convert" \
     -F "target_format=svg" \
     -F "preset=web-interactive-light" \
     -F "file=@commercial_office_floorplan.dwg" \
     -o floorplan_interactive.svg
```

#### Client-Side Dynamic Layer Filtering (JavaScript)
```javascript
// Function to toggle architectural discipline visibility in browser DOM
function setCADLayerVisibility(layerName, isVisible) {
  const layerGroup = document.querySelector(`g[data-layer-name="${layerName}"]`);
  if (layerGroup) {
    layerGroup.style.display = isVisible ? 'inline' : 'none';
  }
}

// Usage examples:
setCADLayerVisibility('A-FURN', false); // Hide furniture
setCADLayerVisibility('E-POWR', true);  // Show electrical lines
```

---

### 2.2 Use Case 2: Municipal Permit & Blueprint Submissions (Vector PDF)
* **Goal**: Generate legally compliant, mathematically exact vector drawing sheets for municipal building departments, architectural plotters, and formal archive retention.
* **Target Format**: `PDF`
* **Optimal Preset**: `monochrome-arch` or `permit-arch-d`
* **Architectural Mechanics**:
  - Enforces pure black strokes (`#000000`) on white paper.
  - Clamps line weights between legal engineering drafting standards ($0.05\text{ pt}$ to $50.0\text{ pt}$).
  - Uses ReportLab vector paths with sub-millimeter affine coordinate transformations, eliminating raster blurriness at 1600% zoom.

#### Production Python Implementation
```python
import requests

def generate_permit_pdf(dwg_path: str, output_pdf_path: str, sheet_size: str = "A1"):
    url = "https://lavinci.rine.studio/convert"
    payload = {
        "target_format": "pdf",
        "preset": "monochrome-arch",
        "options_json": json.dumps({
            "paper_size": sheet_size,
            "orientation": "landscape",
            "line_weight_multiplier": 1.1,
            "draw_dimensions": True
        })
    }
    with open(dwg_path, "rb") as cad_file:
        files = {"file": cad_file}
        response = requests.post(url, data=payload, files=files, timeout=60)
        
    if response.status_code == 200:
        with open(output_pdf_path, "wb") as f:
            f.write(response.content)
        print(f"Permit sheet generated: {output_pdf_path}")
    else:
        raise RuntimeError(f"Conversion failed ({response.status_code}): {response.text}")
```

---

### 2.3 Use Case 3: Multimodal AI Vision & Automated Code Compliance
* **Goal**: Ingest architectural drawings into Multimodal Vision LLMs (GPT-4V, Claude 3.5 Sonnet, Gemini 1.5 Pro) for automated egress code verification, door width calculations, or room label OCR.
* **Target Format**: `PNG`
* **Optimal Preset**: `ai-vision`
* **Architectural Mechanics**:
  - AI models perform poorly on sparse images surrounded by large white margins or black modelspace canvases.
  - The `ai-vision` preset forces 300 DPI resolution, executes auto-fit tight-cropping around the active geometry (protecting the 8px outer border), and ensures high contrast black linework on pure white.

#### Production cURL Implementation
```bash
curl -X POST "https://lavinci.rine.studio/convert" \
     -F "target_format=png" \
     -F "preset=ai-vision" \
     -F "options_json={\"dpi\": 300, \"tight_crop\": true}" \
     -F "file=@hospital_wing.dwg" \
     -o ai_vision_input.png
```

---

### 2.4 Use Case 4: Digital Manufacturing & CAM / CNC / Laser / Plasma Cutting
* **Goal**: Extract flat 2D toolpaths for sheet-metal punching, laser cutters, CNC mills, and waterjet machines.
* **Target Format**: `DXF`
* **Optimal Preset**: `cnc_cam`
* **Architectural Mechanics**:
  - CNC post-processors crash or malfunction if fed 3D coordinates, block definitions, or text.
  - The `cnc_cam` preset synthesizes an AC1009 (DXF R12) file with:
    1. $Z$-coordinates strictly flattened to $0.0$.
    2. All block references (`INSERT`) exploded into raw, loose lines and arcs.
    3. Splines converted into contiguous linear polylines.
    4. Text, dimensions, and visual styles completely stripped.

#### Production Python Implementation
```python
import requests

def export_cnc_toolpaths(dwg_input: str, dxf_output: str):
    url = "https://lavinci.rine.studio/convert"
    payload = {
        "target_format": "dxf",
        "preset": "cnc_cam"
    }
    with open(dwg_input, "rb") as cad_file:
        res = requests.post(url, data=payload, files={"file": cad_file}, timeout=45)
    
    if res.status_code == 200:
        with open(dxf_output, "wb") as out:
            out.write(res.content)
        print("CNC-ready DXF created.")
```

---

### 2.5 Use Case 5: BIM & CAD Coordination Underlays (Revit / Navisworks)
* **Goal**: Import structural or mechanical CAD drawings as 2D coordination underlays in Autodesk Revit or Navisworks without causing layer name collisions.
* **Target Format**: `DXF`
* **Optimal Preset**: `bim_overlay`
* **Architectural Mechanics**:
  - Exports an AC1032 (AutoCAD 2018) DXF.
  - Preserves exact world-coordinate origin $(0, 0, 0)$ for shared positioning.
  - Prepends an `IR_` namespace prefix to all layer names to prevent CAD layers from overriding native Revit project parameters.

---

### 2.6 Use Case 6: Mobile Apps & Real-Estate Property Gallery Feeds
* **Goal**: Generate fast-loading thumbnail images for iOS/Android apps or real-estate portal listing cards.
* **Target Format**: `WebP`
* **Optimal Preset**: `web-thumbnail`
* **Architectural Mechanics**:
  - Produces modern WebP images at 72 DPI capped at 300px maximum dimension.
  - Employs VP8 lossy compression with soft anti-aliasing.
  - Reduces file size to **under 20 KB** (over 80% smaller than comparable PNGs), loading instantly over cellular networks.

---

### 2.7 Use Case 7: Automated Cloud Orchestration via n8n & Webhook Queues
* **Goal**: Automatically convert DWG drawings attached to inbound emails, Slack uploads, or S3 bucket drops.
* **Flow Architecture**:

```
[Inbound CAD File] ──► [n8n Webhook] ──► [HTTP Request: POST /convert] ──► [S3 / Email / Slack]
```

#### n8n Node Specification:
* **Node**: `HTTP Request`
* **Method**: `POST`
* **URL**: `https://lavinci.rine.studio/convert`
* **Body Type**: `Multipart/Form-Data`
* **Fields**:
  - `target_format`: `pdf`
  - `preset`: `presentation-color`
  - `file`: (Binary data stream from incoming node)
* **Response Format**: `File` (Binary stream passed to downstream storage node).

---

## 3. The Deep Edge-Case Encyclopedia: 15 Real-World Anomalies

The La Vinci engine was empirically hardened against a corpus of 922+ production CAD files. Below is the technical breakdown of the 15 most difficult edge cases encountered in real-world CAD processing.

---

### 3.1 Edge Case 1: Non-Coplanar Geometry & Floating $Z$-Coordinates
* **Manifestation**: A user draws a 2D floorplan, but snapping to 3D entities or importing third-party blocks assigns arbitrary $Z$-coordinates (e.g. $Z = 124.52$ or $Z = -0.00012$) to select lines.
* **Downstream Failure**: CNC laser cutters and 2D CAM software error out with *"Entities are non-coplanar"* or refuse to execute continuous toolpaths.
* **Engine Defense**: When compiling via the `cnc_cam` preset or when `flatten_z: true` is passed in `options_json`, `cad-ir-to-dxf` strips all non-zero $Z$ values, strictly projecting every vertex onto the $Z = 0.0$ ground plane:
  $$\vec{P}_{\text{flat}} = [x, y, 0.0]^T$$

---

### 3.2 Edge Case 2: Astronomical Coordinates & Detached Origin Offsets
* **Manifestation**: Civil surveys are drawn in geographic UTM coordinates (e.g. $X = 542,100\text{ m}, Y = 4,210,000\text{ m}$), or drafters leave a forgotten reference tick at $(0, 0)$.
* **Downstream Failure**: Standard bounding box calculations span from $0$ to $4.2\times 10^6$. The actual building shrinks to a microscopic sub-pixel speck, producing an apparently "blank" white image.
* **Engine Defense**:
  1. `find_primary_cluster_1d` calculates 1D coordinate histograms across both axes. Any gap exceeding $5\times$ the median inter-entity distance is identified as empty space.
  2. The primary cluster containing the true geometry density is isolated.
  3. The tight-crop pass in `cad-ir-to-raster` scans for actual pixel bounding envelopes and trims empty space automatically.

---

### 3.3 Edge Case 3: Arc Chirality Inversion under Vertical Reflection (The Phantom Arc)
* **Manifestation**: In AutoCAD, analytic arcs are parameterized with counter-clockwise (CCW) sweeps in a $+Y$ upwards coordinate frame.
* **Downstream Failure**: Screen and web coordinates (SVG) invert the vertical axis ($+Y$ points down). Direct angle inheritance with `sweep_flag = 0` causes the arc to visually reflect into an inverted, ballooning curve that sweeps outside the canvas.
* **Mathematical Derivation**:
  Vertical reflection across the horizontal axis inverts rotational chirality:
  $$\text{Chirality}(\vec{v}) = \text{sign}\left(\det \begin{bmatrix} x_1 & x_2 \\ y_1 & y_2 \end{bmatrix}\right)$$
  $$\det \begin{bmatrix} x_1 & x_2 \\ -y_1 & -y_2 \end{bmatrix} = -\det \begin{bmatrix} x_1 & x_2 \\ y_1 & y_2 \end{bmatrix} \implies \text{CCW} \mapsto \text{CW}$$
* **Engine Defense**: The SVG compiler strictly forces `sweep_flag = 1` (Clockwise) for all Y-inverted circular arcs, guaranteeing that curves follow their intended physical trajectory.

---

### 3.4 Edge Case 4: Rotated & Vertical Text Annotations (The Bugatti Chiron Case)
* **Manifestation**: Automotive and mechanical drawings feature dimensions aligned along angled chassis rails, vertical title blocks, or text tags rotated at $90^\circ, 180^\circ$, or arbitrary radians.
* **Downstream Failure**: Parsers extract coordinate positions but drop the DXF `50` rotation angle. Renderers draw all text horizontally, creating overlapping linework collisions and unreadable vertical dimensions.
* **Engine Defense**:
  1. `cad-extractor-ir` extracts the exact rotation angle and stores it in `CADAnnotation.rotation`.
  2. In `cad-ir-to-pdf`, text rendering is isolated using ReportLab canvas transformation stacks:
     ```python
     c.saveState()
     c.translate(transformed_x, transformed_y)
     c.rotate(ann.rotation)
     c.drawString(0, 0, ann.clean_text)
     c.restoreState()
     ```
  3. The text is drawn with exact angular alignment without disturbing subsequent canvas operations.

---

### 3.5 Edge Case 5: Background Contrast Collisions & Rec. 709 Luminance
* **Manifestation**: Drafters assign linework color to pure white (`#FFFFFF`) or pale yellow because native AutoCAD uses a black modelspace.
* **Downstream Failure**: Rendered onto white paper or a light SVG canvas, white lines vanish completely. Conversely, black linework vanishes on dark blueprint presets.
* **Engine Defense**:
  `cad-ir-to-pdf` and `cad-ir-to-svg` execute ITU-R Recommendation BT.709 relative luminance analysis:
  $$Y = 0.2126R + 0.7152G + 0.0722B$$
  * On light canvases ($Y_{\text{bg}} \ge 0.2$): Any stroke with $Y_{\text{stroke}} > 0.95$ is dynamically remapped to high-contrast black (`#000000`).
  * On dark canvases ($Y_{\text{bg}} < 0.2$): Any stroke with $Y_{\text{stroke}} \le 0.10$ is dynamically inverted to pure white (`#FFFFFF`).

---

### 3.6 Edge Case 6: Upstream Binary Data Loss (The Patient Chairs Case)
* **Manifestation**: DWG files created by specialized vertical add-ons (AutoCAD Architecture, Civil 3D) contain proprietary 3D ACIS solids or corrupted object handles.
* **Downstream Failure**: Open-source C libraries (GNU LibreDWG) drop these unrecognized handles during decompilation (e.g. omitting the armrest handle of Block 27 in a chair drawing). The downstream renderer faithfully draws what it received, producing a seemingly broken line.
* **Engine Defense**:
  Because binary C libraries cannot be completely rewritten from userland, La Vinci implements **Transparent Extraction Warnings**:
  1. Captures `stderr` output from the `dwg2dxf` subprocess.
  2. Scans for `Warning:` and `ERROR:` strings.
  3. Exposes harvested warnings directly in the API JSON response under `diagnostics.warnings`. Clients can alert users that proprietary upstream entities were dropped.

---

### 3.7 Edge Case 7: Lone Unicode Surrogates & International Charsets
* **Manifestation**: Obfuscated CAD files or drawings authored in Asian locales (Shift-JIS, CP932, Big5) often contain isolated half-surrogate code points ($0\text{xD800} \le c \le 0\text{xDFFF}$).
* **Downstream Failure**: Standard Python `json.dumps()` raises fatal `UnicodeEncodeError` exceptions, causing the API to crash with a 500 internal server error.
* **Engine Defense**: All text strings pass through `sanitize_surrogates()`, which encodes with `surrogatepass` and decodes with replacement before JSON serialization.

---

### 3.8 Edge Case 8: Circular Block Recursion & Deep Hierarchies
* **Manifestation**: Corrupted drawings can define Block A inserting Block B, which in turn inserts Block A.
* **Downstream Failure**: Recursive expansion triggers call-stack overflow or infinite memory allocation loops.
* **Engine Defense**:
  1. Clamps recursion depth to a maximum of **16 levels**.
  2. `cad-ir-to-dxf` performs pre-compilation depth-first cycle detection (`check_block_cycles`), failing fast with a clean `BlockCycleError` if a loop is detected.

---

### 3.9 Edge Case 9: Node Density & Spline "Chattering" in CNC Machining
* **Manifestation**: Complex spline curves extracted with millions of microscopic control vertices.
* **Downstream Failure**: CNC controllers suffer from buffer underruns, causing cutting heads to stutter ("chatter") and leaving jagged gouges in cut metal.
* **Engine Defense**: When `curve_strategy="splines_to_polylines"` is enabled, the engine approximates splines using bi-arc fitting with a configurable chord deviation tolerance (`tessellation_distance: 2.0`), optimizing vertex density for smooth machine feedrates.

---

### 3.10 Edge Case 10: Hatch Pattern Explosions & Non-Closed Boundaries
* **Manifestation**: Dense cross-hatch patterns drawn across unclosed or self-intersecting boundaries.
* **Downstream Failure**: AutoCAD's `HPMAXLINES` limit is exceeded, or vector rendering generates hundreds of thousands of microscopic lines, crashing SVG parsers with XML file sizes $> 100\text{ MB}$.
* **Engine Defense**: In `cad-extractor-ir`, unclosed hatch boundaries are detected and skipped; dense pattern lines are simplified or isolated on dedicated layers so clients can exclude them if needed.

---

### 3.11 Edge Case 11: SHX Font Vectors vs TrueType Strings
* **Manifestation**: Legacy drawings utilize AutoCAD compile-font `.shx` files.
* **Downstream Failure**: SHX fonts are drawn as un-encoded raw vector lines rather than text characters, bloating file sizes and making text unsearchable in PDF outputs.
* **Engine Defense**: When TrueType annotations (`TEXT`/`MTEXT`) are available, clean text strings are extracted into `CADAnnotation`. SHX vector linework is preserved cleanly as lines without duplicate character overlaps.

---

### 3.12 Edge Case 12: Viewport Matrix Transformations in Paper Space
* **Manifestation**: A drawing has its model geometry in Model Space, but title blocks, notes, and scaled views are organized inside Paper Space layout tabs.
* **Downstream Failure**: Renderers conflate Model and Paper spaces, drawing layout borders directly on top of raw floorplans.
* **Engine Defense**: `LAVINCI_CAD_IR_V3` strictly segregates `space: "Model"` from paper layout tabs (`CADLayout`). Compilers default to rendering the primary Model Space or allow explicit selection via `target_space`.

---

### 3.13 Edge Case 13: Degenerate Geometry & Microscopic Line Segments
* **Manifestation**: CAD cleanup routines or imperfect snapping create zero-length line segments where start point equals end point:
  $$\|\vec{P}_{\text{end}} - \vec{P}_{\text{start}}\|_2 < 1.0 \times 10^{-9}$$
* **Downstream Failure**: Division-by-zero during slope and normal vector calculations, crashing vector renderers.
* **Engine Defense**: Entities with length below `zero_length_tolerance` are filtered out during pre-compilation sanitization.

---

### 3.14 Edge Case 14: Unit Discrepancies ($25.4\times$ Scaling Errors)
* **Manifestation**: Drawing geometry was authored in inches, but the header `$INSUNITS` variable was left at `0` (Unitless) or set to `4` (Millimeters).
* **Downstream Failure**: When linked into architectural models, drawings appear $25.4\times$ too small or $25.4\times$ too large.
* **Engine Defense**: `cad-extractor-ir` records both `$INSUNITS` and `$MEASUREMENT` in metadata and provides a `fixed_scale` parameter in `PdfOptions` and `AdvancedOptions` to allow clients to scale coordinates by $25.4$ or $0.03937$ on the fly.

---

### 3.15 Edge Case 15: Extreme Dynamic Line Weight Scaling
* **Manifestation**: An architectural floorplan spans $50\text{ meters}$, while a detail vignette in the same file measures $50\text{ mm}$.
* **Downstream Failure**: Hardcoded stroke widths render lines either microscopic or completely bloated.
* **Engine Defense**: Dynamic stroke width scaling based on the bounding box diagonal:
  $$\text{stroke\_width} = \max\left(0.1, \; 0.001 \times \sqrt{\text{width}^2 + \text{height}^2}\right)$$
  Guarantees visually balanced linework regardless of drawing scale.

---

## 4. Troubleshooting Runbook & Error Code Reference

When integrating with `https://lavinci.rine.studio`, refer to this matrix for rapid resolution of HTTP status codes and conversion exceptions:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       HTTP ERROR RESOLUTION MATRIX                          │
├─────────┬───────────────────────────────┬───────────────────────────────────┤
│ Status  │ Root Cause                    │ Actionable Resolution             │
├─────────┼───────────────────────────────┼───────────────────────────────────┤
│ 400     │ Field exceeded maximum size   │ IR JSON string was sent in a form │
│         │ limit (1024 KB form field)    │ field; pass it as a file upload   │
│         │                               │ or convert raw CAD directly.      │
├─────────┼───────────────────────────────┼───────────────────────────────────┤
│ 422     │ Unsupported target_format     │ Must be one of: pdf, svg, png,    │
│         │                               │ jpeg, webp, dxf.                  │
├─────────┼───────────────────────────────┼───────────────────────────────────┤
│ 422     │ Ambiguous input provided      │ Pass 'file' OR 'ir_json', not     │
│         │                               │ both in the same request.         │
├─────────┼───────────────────────────────┼───────────────────────────────────┤
│ 422     │ Invalid options JSON          │ Verify options_json syntax; must  │
│         │                               │ be valid JSON (e.g. {"dpi":300}). │
├─────────┼───────────────────────────────┼───────────────────────────────────┤
│ 504     │ Execution timeout             │ Drawing contains >300k entities or│
│         │                               │ Lambda cold start; increase       │
│         │                               │ client timeout to 60 seconds.     │
├─────────┼───────────────────────────────┼───────────────────────────────────┤
│ 500     │ Unhandled parser panic        │ Verify drawing is not corrupted;  │
│         │                               │ run AUDIT/PURGE in AutoCAD.       │
└─────────┴───────────────────────────────┴───────────────────────────────────┘
```

---

## 5. Security & DoS Protection Invariants

Operating a public CAD conversion API introduces unique security attack surfaces that La Vinci actively mitigates:

1. **Decompression & XML Entity Expansion (Billion Laughs)**:
   - Ingested files never execute un-sandboxed XML entity parsing.
   - SVG outputs are synthesized programmatically via string templates rather than unvalidated XML DOM tree expansions.
2. **Infinite Subprocess Loops**:
   - Every invocation of LibreDWG is wrapped in an adaptive Python subprocess timeout supervisor. Unresponsive processes are terminated via `SIGKILL` after the timeout expires.
3. **Memory Isolation**:
   - AWS Lambda runs each conversion in an ephemeral microVM container (Firecracker). Memory allocations are strictly contained to **2,048 MB**, preventing memory leak accumulation across user requests.
4. **Temporary File Scrubbing**:
   - All disk-backed operations execute inside isolated `tempfile.NamedTemporaryFile` workspaces and are strictly purged in `finally` blocks, leaving zero leftover artifacts on disk.
