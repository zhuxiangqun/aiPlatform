from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


BBox = Tuple[int, int, int, int]  # x1,y1,x2,y2 in pixels


@dataclass
class OCRToken:
    text: str
    bbox: BBox
    conf: float = 0.0


@dataclass
class Citation:
    """
    证据引用：用于前端定位。
    - page_idx: 0-based
    - asset_path: 渲染出来的页面图片（或裁剪出来的图表区域）
    - bbox: 在 asset_path 坐标系中的矩形
    """

    page_idx: int
    asset_path: str
    bbox: Optional[BBox] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedNumber:
    value_raw: str
    value: Optional[float]
    token: OCRToken
    context: str = ""


@dataclass
class IngestResult:
    doc_id: str
    pdf_path: str
    page_images: List[str]
    ocr_by_page: List[List[OCRToken]]
    numbers_by_page: List[List[ExtractedNumber]]
    tables_by_page: Optional[List[List[Dict[str, Any]]]] = None  # list of structured tables per page (PoC)


@dataclass
class QAResult:
    answer: str
    citations: List[Citation] = field(default_factory=list)
    debug: Dict[str, Any] = field(default_factory=dict)
