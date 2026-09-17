"""
telemetry.py - Structured compilation reporting for cad-ir-to-raster.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RasterReport:
    """
    Structured report describing the outcome of a single IR-to-raster compilation.
    """
    output_target: str = "<in-memory>"
    success: bool = False
    preset_name: str = "web-preview"
    format: str = "png"
    dpi: int = 150
    pixel_width: int = 0
    pixel_height: int = 0
    file_size_bytes: int = 0
    total_entities_read: int = 0
    total_entities_rendered: int = 0
    total_entities_dropped: int = 0
    cad_bbox_extents: Dict[str, float] = field(default_factory=dict)
    tight_crop_applied: bool = False
    render_time_ms: float = 0.0
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None
