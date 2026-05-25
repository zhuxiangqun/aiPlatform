from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from core.utils.ids import new_prefixed_id

from .extract_numbers import extract_numbers
from .ocr import choose_best_ocr_engine, ocr_image
from .pdf_render import render_pdf_to_images
from .table_extract import extract_budget_table
from .types import IngestResult


def ingest_scanned_pdf(
    pdf_path: str,
    *,
    out_dir: str,
    dpi: int = 220,
    max_pages: Optional[int] = None,
    ocr_lang: str = "zh",
    ocr_engine: Optional[str] = None,
    progress_cb: Optional[Callable[[float, str, Dict[str, Any]], None]] = None,
) -> IngestResult:
    """
    PoC：扫描 PDF → 渲染页图 → OCR（带 bbox）→ 抽取候选数值。

    输出写到 out_dir：
    - pages/page_0000.png ...
    """
    pdf_path = str(pdf_path)
    out_base = Path(out_dir)
    out_base.mkdir(parents=True, exist_ok=True)

    # stable-ish doc_id
    try:
        sha = hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()[:12]
        doc_id = f"doc_{sha}"
    except Exception:
        doc_id = new_prefixed_id("doc")

    pages_dir = out_base / doc_id / "pages"
    if progress_cb:
        progress_cb(0.05, "render_start", {"dpi": dpi, "max_pages": max_pages})
    pages = render_pdf_to_images(pdf_path, out_dir=str(pages_dir), dpi=dpi, max_pages=max_pages)
    if progress_cb:
        progress_cb(0.15, "render_done", {"pages": len(pages)})

    engine = (ocr_engine or choose_best_ocr_engine()).strip().lower()

    ocr_by_page = []
    numbers_by_page = []
    tables_by_page = []
    for i, img_path in enumerate(pages):
        if progress_cb and len(pages) > 0:
            # 0.15 ~ 0.90 reserved for per-page OCR+table extract
            p = 0.15 + 0.75 * float(i) / float(len(pages))
            progress_cb(p, "ocr_page_start", {"page_idx": i, "pages": len(pages), "image": str(img_path), "engine": engine})
        # progress hint (visible in core logs)
        try:
            print(f"[kb_ingest] OCR page {i+1}/{len(pages)}: {img_path}")
        except Exception:
            pass
        tokens = ocr_image(img_path, engine="paddleocr" if engine == "paddleocr" else "tesseract", lang=ocr_lang)
        # For budget-like questions, a larger context window helps keep headers (预算/年度/单位) close to numbers.
        nums = extract_numbers(tokens, window=15)
        tables = extract_budget_table(tokens)
        ocr_by_page.append(tokens)
        numbers_by_page.append(nums)
        tables_by_page.append(tables)
        if progress_cb and len(pages) > 0:
            p = 0.15 + 0.75 * float(i + 1) / float(len(pages))
            progress_cb(p, "ocr_page_done", {"page_idx": i, "pages": len(pages), "tables": len(tables or [])})

    if progress_cb:
        progress_cb(0.92, "extract_done", {"pages": len(pages)})

    return IngestResult(
        doc_id=doc_id,
        pdf_path=pdf_path,
        page_images=pages,
        ocr_by_page=ocr_by_page,
        numbers_by_page=numbers_by_page,
        tables_by_page=tables_by_page,
    )
