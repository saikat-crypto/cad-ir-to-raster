"""
telemetry.py — Structured compilation reporting for cad-ir-to-raster.

RasterReport is returned optionally alongside the raster output, providing
full observability into what the engine processed, dropped, and produced.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class RasterReport:
    """
    Structured report describing the outcome of a single IR-to-raster compilation.
    Returned alongside the compiled output when return_report=True.
    """
    # Output target (file path or "<in-memory>")
    output_target: str = "<in-memory>"

    # Success flag
    success: bool = False

    # Preset used for this compilation
    preset_name: str = "web-preview"
    format: str = "png"
    dpi: int = 150

    # Rendered image dimensions
    pixel_width: int = 0
    pixel_height: int = 0
    file_size_bytes: int = 0

    # Entity counts
    total_entities_read: int = 0
    total_entities_rendered: int = 0
    total_entities_dropped: int = 0

    # CAD drawing geometry metrics
    cad_bbox_extents: Dict[str, float] = field(default_factory=dict)

    # Timing
    render_time_ms: float = 0.0

    # Warnings list (sanitization events, fallbacks applied, etc.)
    warnings: List[str] = field(default_factory=list)

    # Error message if success=False
    error: Optional[str] = None
