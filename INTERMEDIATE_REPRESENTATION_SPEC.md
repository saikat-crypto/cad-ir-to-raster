# LAVINCI_CAD_IR_V3: Intermediate Representation Specification & Reference Manual

> **Document Version**: `3.0.0`  
> **Target Standard**: `LAVINCI_CAD_IR_V3`  
> **Schema Definition**: `cad_extractor.models.CADIntermediateRepresentation`  
> **Classification**: Core Architectural Invariant  

---

## 1. Philosophical Basis & Architectural Invariant

The **LAVINCI_CAD_IR_V3** is the universal interchange format and single source of truth across the entire La Vinci ecosystem. 

In traditional CAD software ecosystems, conversions between file formats suffer from the $O(N^2)$ combinatorial explosion problem: converting between $N$ formats requires $N \times (N-1)$ bespoke converters. In addition to development overhead, point-to-point converters inevitably accumulate conversion drift, compounding coordinate inaccuracies, dropped entity types, and loss of metadata.

```
Traditional Point-to-Point ($O(N^2)$):
DWG ───► DXF ───► SVG ───► PDF ───► PNG (Compound drift & entity loss)

La Vinci Hub-and-Spoke Invariant ($O(N)$):
                  ┌──────────────────────┐
                  │   CAD Input File     │
                  │ (.dwg / .dxf / .dwt) │
                  └──────────┬───────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │   LAVINCI_CAD_IR_V3 (JSON)   │
              └──────────────┬───────────────┘
         ┌───────────┬───────┴───────┬───────────┐
         ▼           ▼               ▼           ▼
     Vector PDF     SVG         AutoCAD DXF    Raster
```

### Core Design Principles
1. **Canonical Neutrality**: The IR does not assume any display medium. It preserves raw, unprojected modelspace coordinates without premature pixel rasterization, page imposition, or DPI quantization.
2. **Lossless Geometric Decomposition**: Curves, analytic arcs, polylines, and block references retain their mathematical definitions (centers, radii, sweep angles, bulge factors, scale vectors) rather than being destructively tessellated during extraction.
3. **Strict Serialization**: The entire IR model is 100% JSON-serializable, validatable via Pydantic v2, and deterministic across operating systems (Windows, Linux, macOS).
4. **Resilience & Diagnostic Visibility**: Upstream binary parser errors (such as GNU LibreDWG handle drops) are captured directly in the metadata rather than causing pipeline panics.

---

## 2. Global Coordinate Space & Unit System

AutoCAD and DXF represent geometry in an arbitrary Cartesian coordinate system with $+Y$ oriented **upwards** (standard mathematical right-handed convention).

$$\vec{P} = \begin{bmatrix} x \\ y \\ z \end{bmatrix} \in \mathbb{R}^3$$

### 2.1 Coordinate Bounds & Numerical Guardrails
To prevent numerical overflow, division-by-zero, and floating-point corruption, all coordinate streams ingested into the IR are sanitized against physical CAD boundaries:

$$\text{MAX\_PHYSICAL\_CAD\_COORD} = 1.0 \times 10^9$$
$$\text{MIN\_NONZERO\_CAD\_COORD} = 1.0 \times 10^{-9}$$

Any vertex or transformation yielding $\text{NaN}$, $\pm\infty$, or $|x| > 10^9$ is filtered or clamped prior to serialization.

### 2.2 Measurement System & Units Code
The IR explicitly preserves `$INSUNITS` and `$MEASUREMENT` from the CAD header:

| Code (`units`) | Drawing Unit | System |
| :---: | :--- | :--- |
| `0` | Unspecified / Unitless | Inherited |
| `1` | Inches | Imperial |
| `2` | Feet | Imperial |
| `4` | Millimeters | Metric |
| `5` | Centimeters | Metric |
| `6` | Meters | Metric |

---

## 3. Exhaustive Schema & Data Model Specification

The IR root is defined by the Pydantic model `CADIntermediateRepresentation`.

### 3.1 Root Structure

```json
{
  "format": "LAVINCI_CAD_IR_V3",
  "metadata": { ... },
  "extents": { ... },
  "layouts": [ ... ],
  "layers": [ ... ],
  "bill_of_materials": { ... },
  "block_definitions": { ... },
  "annotations": [ ... ],
  "dimensions": [ ... ],
  "components": [ ... ],
  "geometry_primitives": { ... }
}
```

---

### 3.2 Metadata Block (`CADMetadata`)

Encapsulates global drawing properties, author information, AutoCAD release vintage, and parser diagnostics.

| Field | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `source_file` | `str` | Required | Original filename or identifier of the source file. |
| `dxf_version` | `str` | e.g. `AC1015`, `AC1021`, `AC1027`, `AC1032` | Internal AutoCAD header version string. |
| `cad_version` | `str` | e.g. `AutoCAD 2007`, `AutoCAD 2018` | Human-readable AutoCAD release designation. |
| `units` | `int` | $0 \le \text{units} \le 24$ | AutoCAD `$INSUNITS` index code. |
| `measurement_system` | `str` | `"Metric"` or `"Imperial"` | Derived from `$MEASUREMENT` header variable. |
| `author` | `Optional[str]` | Default `"Unknown"` | Creator login name extracted from `$LOGINNAME`. |
| `extraction_warnings` | `List[str]` | Default `[]` | Diagnostic messages, dropped handles, or unstable classes emitted by upstream parsers. |

#### Example
```json
{
  "source_file": "floorplan-level1.dwg",
  "dxf_version": "AC1027",
  "cad_version": "AutoCAD 2013",
  "units": 4,
  "measurement_system": "Metric",
  "author": "Architectural Studio A",
  "extraction_warnings": [
    "Warning: Object handle not found 314343 in 12208 objects",
    "Warning: Unstable Class object 505 MATERIAL"
  ]
}
```

---

### 3.3 Extents Block (`CADExtents`)

Represents the outer bounding envelope enclosing all active geometry in Model Space.

$$\text{width} = X_{\max} - X_{\min}$$
$$\text{height} = Y_{\max} - Y_{\min}$$
$$\text{diagonal} = \sqrt{\text{width}^2 + \text{height}^2}$$

| Field | Type | Description |
| :--- | :--- | :--- |
| `min` | `List[float]` | 2D vector $[X_{\min}, Y_{\min}]$ of minimum physical coordinates. |
| `max` | `List[float]` | 2D vector $[X_{\max}, Y_{\max}]$ of maximum physical coordinates. |
| `width` | `float` | Span along the X-axis in drawing units. |
| `height` | `float` | Span along the Y-axis in drawing units. |

---

### 3.4 Layer Table (`CADLayer`)

Represents AutoCAD layer state, colors, visibility, and line styling.

| Field | Type | Description |
| :--- | :--- | :--- |
| `name` | `str` | Unique layer name (e.g., `"A-WALL"`, `"0"`, `"DEFPOINTS"`). |
| `color_aci` | `int` | AutoCAD Color Index ($0 \le \text{ACI} \le 256$). $7 = \text{Black/White}$. |
| `hex_color` | `str` | Canonical 24-bit hexadecimal RGB string (`"#RRGGBB"`). |
| `is_off` | `bool` | True if the layer visibility is toggled off. |
| `is_locked` | `bool` | True if the layer is locked against modification. |
| `is_frozen` | `bool` | True if the layer is frozen in model space. |
| `linetype` | `str` | Standard linetype (e.g., `"CONTINUOUS"`, `"DASHED"`, `"HIDDEN"`). |

---

### 3.5 Geometric Primitives (`CADGeometry`)

Contains the core visual vector elements partitioned into lines, arcs, circles, and polylines.

#### 3.5.1 Linear Segment (`CADLine`)
Represents an analytic straight line between two points.

$$\vec{P}(t) = \vec{S} + t(\vec{E} - \vec{S}), \quad t \in [0, 1]$$

* `layer` (`str`): Name of the parent layer.
* `space` (`str`): Target space (`"Model"` or paper layout name).
* `start` (`List[float]`): $[X_1, Y_1]$ coordinate pair.
* `end` (`List[float]`): $[X_2, Y_2]$ coordinate pair.
* `color` (`Optional[str]`): Explicit hex color override; `null` indicates inheritance via `BYLAYER`.
* `linetype` (`Optional[str]`): Explicit linetype override; `null` indicates `BYLAYER`.

#### 3.5.2 Analytic Circular Arc (`CADArc`)
Represents a circular curve traversing counter-clockwise from start angle to end angle in CAD space.

$$\theta(t) = \theta_s + t(\theta_e - \theta_s), \quad x(t) = C_x + R\cos\theta(t), \quad y(t) = C_y + R\sin\theta(t)$$

* `layer` (`str`): Parent layer.
* `space` (`str`): `"Model"` or paper space.
* `center` (`List[float]`): $[C_x, C_y]$ center coordinate.
* `radius` (`float`): Radius $R > 0$ in drawing units.
* `start_angle` (`float`): Start angle $\theta_s \in [0, 360)$ degrees.
* `end_angle` (`float`): End angle $\theta_e \in [0, 360)$ degrees.
* `color` / `linetype`: Optional explicit overrides.

#### 3.5.3 Complete Circle (`CADCircle`)
* `center` (`List[float]`): $[C_x, C_y]$ center coordinate.
* `radius` (`float`): Radius $R > 0$.
* `layer`, `space`, `color`, `linetype`: Standard attributes.

#### 3.5.4 Multi-Segment Polyline (`CADPolyline`)
Represents contiguous piecewise linear or curved segments (AutoCAD `LWPOLYLINE` or `POLYLINE2D`).

$$\mathcal{P} = \{ \vec{p}_0, \vec{p}_1, \vec{p}_2, \dots, \vec{p}_n \}$$

* `points` (`List[List[float]]`): Ordered array of $[x, y]$ vertex coordinates. Any curved segments defined by AutoCAD bulge factors ($b = \tan(\Delta\theta/4)$) are mathematically tessellated into planar vertices during extraction.
* `is_closed` (`bool`): `true` if the polyline forms a closed boundary connecting $\vec{p}_n \to \vec{p}_0$.

---

### 3.6 Block Definitions & Component Instances

La Vinci IR supports reusable hierarchical block definitions (`BLOCK`) and their spatial insertions (`INSERT`).

#### Block Definition (`CADBlockDefinition`)
* `name` (`str`): Block name identifier (e.g., `"_Chair_Standard"`, `"DOOR_900"`).
* `base_point` (`List[float]`): Insertion base offset $[X_b, Y_b, Z_b]$.
* `lines`, `arcs`, `circles`, `polylines`: Geometry primitives defined in block-local coordinates.

#### Component Instance (`CADComponentInstance`)
Represents a transformed instance of a block inserted into Model Space.

* `block_name` (`str`): Reference to the key in `block_definitions`.
* `position` (`List[float]`): Insertion location $[X, Y]$ in parent coordinates.
* `rotation` (`float`): Rotation angle $\alpha$ in degrees counter-clockwise.
* `scale` (`List[float]`): Scale vector $[S_x, S_y, S_z]$.
* `attributes` (`Dict[str, str]`): Key-value dictionary of block attribute tags (`ATTRIB`).

#### Mathematical Transformation Matrix
Every component instance projects local block geometry $\vec{P}_{\text{local}}$ into global world space $\vec{P}_{\text{world}}$ via the affine transformation:

$$\vec{P}_{\text{world}} = \begin{bmatrix} S_x \cos\alpha & -S_y \sin\alpha \\ S_x \sin\alpha & S_y \cos\alpha \end{bmatrix} (\vec{P}_{\text{local}} - \vec{P}_{\text{base}}) + \begin{bmatrix} X_{\text{pos}} \\ Y_{\text{pos}} \end{bmatrix}$$

---

### 3.7 Annotations & Text Entities (`CADAnnotation`)

Represents text labels, title blocks, and notes (`TEXT` and `MTEXT`).

* `type` (`str`): Source entity type (`"TEXT"` or `"MTEXT"`).
* `layer` (`str`): Target layer.
* `space` (`str`): Active space (`"Model"` or layout name).
* `raw_text` (`str`): Raw unescaped string with AutoCAD formatting codes (e.g., `\\A1;{\\H1.5x;Text}`).
* `clean_text` (`str`): Sanitized, human-readable plain text with formatting codes stripped.
* `position` (`List[float]`): Insertion alignment coordinate $[X, Y]$.
* `height` (`float`): Nominal font height in drawing units.
* `rotation` (`float`): Text orientation angle in degrees ($0 \le \theta < 360$). Crucial for vertical dimensions and rotated tags.

---

### 3.8 Dimensions (`CADDimension`)

Represents linear, aligned, radial, and angular dimension entities.

* `type` (`str`): Dimension classification (`"LINEAR"`, `"ALIGNED"`, `"ANGULAR"`, `"DIAMETER"`).
* `measurement` (`Optional[float]`): Actual computed numerical distance in drawing units.
* `text` (`Optional[str]`): Formatted dimension text (e.g., `"2500 mm"` or `"<>"`).
* `defpoint` (`List[float]`): Primary definition point $[X, Y]$.
* `defpoint2` (`Optional[List[float]]`): Secondary definition point for linear extents.
* `text_midpoint` (`Optional[List[float]]`): Position $[X, Y]$ of the dimension label text.
* `text_height` (`Optional[float]`): Font height of the dimension text.
* `text_rotation` (`Optional[float]`): Rotation of the dimension label.

---

### 3.9 Bill of Materials (`bill_of_materials`)

An automatically computed frequency map of all component instances across the drawing:

```json
{
  "Clinicians_Chair_27": 12,
  "Door_Single_900x2100": 34,
  "Window_Double_1200x1500": 18,
  "Structural_Column_W310": 48
}
```

---

## 4. Complete Canonical JSON Example

```json
{
  "format": "LAVINCI_CAD_IR_V3",
  "metadata": {
    "source_file": "sample_structure.dwg",
    "dxf_version": "AC1027",
    "cad_version": "AutoCAD 2013",
    "units": 4,
    "measurement_system": "Metric",
    "author": "Chief Engineer",
    "extraction_warnings": []
  },
  "extents": {
    "min": [-150.0, -100.0],
    "max": [4850.0, 3200.0],
    "width": 5000.0,
    "height": 3300.0
  },
  "layouts": [
    {
      "name": "Model",
      "is_active": true,
      "extents_min": [-150.0, -100.0],
      "extents_max": [4850.0, 3200.0],
      "viewports": []
    }
  ],
  "layers": [
    {
      "name": "0",
      "color_aci": 7,
      "hex_color": "#000000",
      "is_off": false,
      "is_locked": false,
      "is_frozen": false,
      "linetype": "CONTINUOUS"
    },
    {
      "name": "WALLS",
      "color_aci": 1,
      "hex_color": "#FF0000",
      "is_off": false,
      "is_locked": false,
      "is_frozen": false,
      "linetype": "CONTINUOUS"
    }
  ],
  "bill_of_materials": {
    "DOOR_SINGLE": 4
  },
  "block_definitions": {
    "DOOR_SINGLE": {
      "name": "DOOR_SINGLE",
      "base_point": [0.0, 0.0, 0.0],
      "lines": [
        {
          "layer": "0",
          "space": "Model",
          "start": [0.0, 0.0],
          "end": [900.0, 0.0],
          "color": null,
          "linetype": null
        }
      ],
      "arcs": [
        {
          "layer": "0",
          "space": "Model",
          "center": [0.0, 0.0],
          "radius": 900.0,
          "start_angle": 0.0,
          "end_angle": 90.0,
          "color": null,
          "linetype": null
        }
      ],
      "circles": [],
      "polylines": []
    }
  },
  "annotations": [
    {
      "type": "TEXT",
      "layer": "TEXT",
      "space": "Model",
      "raw_text": "ENTRANCE FOYER",
      "clean_text": "ENTRANCE FOYER",
      "position": [450.0, 200.0],
      "height": 150.0,
      "rotation": 0.0
    }
  ],
  "dimensions": [
    {
      "type": "LINEAR",
      "layer": "DIMS",
      "space": "Model",
      "measurement": 5000.0,
      "text": "5000",
      "defpoint": [0.0, 0.0],
      "defpoint2": [5000.0, 0.0],
      "text_midpoint": [2500.0, -100.0],
      "text_height": 100.0,
      "text_rotation": 0.0
    }
  ],
  "components": [
    {
      "block_name": "DOOR_SINGLE",
      "resolved_name": "DOOR_SINGLE",
      "layer": "WALLS",
      "space": "Model",
      "position": [1200.0, 0.0],
      "rotation": 90.0,
      "scale": [1.0, 1.0, 1.0],
      "attributes": {}
    }
  ],
  "geometry_primitives": {
    "summary": {
      "total_lines": 1,
      "total_arcs": 0,
      "total_circles": 0,
      "total_polylines": 0,
      "total_components": 1,
      "total_annotations": 1,
      "total_dimensions": 1,
      "total_block_definitions": 1
    },
    "primitives": {
      "lines": [
        {
          "layer": "WALLS",
          "space": "Model",
          "start": [0.0, 0.0],
          "end": [5000.0, 0.0],
          "color": null,
          "linetype": null
        }
      ],
      "arcs": [],
      "circles": [],
      "polylines": []
    }
  }
}
```

---

## 5. Downstream Compiler Invariants

Every compiler consuming the `LAVINCI_CAD_IR_V3` must observe the following guarantees:

1. **`BYLAYER` Resolution**: When an entity's `color` or `linetype` is `null`, the compiler must query the `layers` table using the entity's `layer` property to determine the effective stroke color and line pattern.
2. **Text Extents Protection**: When calculating viewBox or page layout bounds, `annotations` must not be pruned by outlier algorithms; bounding box calculations must enclose text height and character spans.
3. **Rotation Processing**: Compilers must respect the `rotation` field on `CADAnnotation` and `CADComponentInstance`, applying affine rotation transformations prior to translation.
