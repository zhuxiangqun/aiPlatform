"""POC Data Injector handler — 客户数据快速注入 (FDE POC)."""
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

log = logging.getLogger("poc_inject")

_HANDLERS = {
    ".pdf": "pdf", ".png": "pdf", ".jpg": "pdf", ".jpeg": "pdf",
    ".csv": "csv", ".xlsx": "excel", ".xls": "excel",
    ".txt": "text", ".md": "text",
}

_POC_KB = os.path.expanduser("~/.aiplat/kb/poc")


def _save_as_document(file_path: str, content: str, fmt: str = "text") -> str:
    os.makedirs(_POC_KB, exist_ok=True)
    doc_id = f"poc-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    meta = {"source": file_path, "format": fmt, "ingested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
    with open(os.path.join(_POC_KB, f"{doc_id}.json"), "w", encoding="utf-8") as f:
        json.dump({"id": doc_id, "content": content, "meta": meta}, f, ensure_ascii=False)
    return doc_id


def _inject_pdf(file_path: str) -> dict:
    """PDF → text using core's existing OCR infrastructure.
    
    Dual-path: native text extraction (fast, digital PDFs) → OCR fallback
    (render pages as images, then Tesseract/PaddleOCR via InfraOCRAdapter).
    All dependencies are already in core — zero cross-layer imports.
    """
    import os as _os, tempfile as _tempfile

    try:
        import fitz  # type: ignore  # PyMuPDF — already in core (parsers.py:205)
    except ImportError:
        return {"status": "error", "error": "PyMuPDF not available", "pages": 0, "method": "unavailable"}

    doc = fitz.open(file_path)
    page_count = doc.page_count

    # ── Fast path: native text for digital PDFs ──
    native_texts = [p.get_text().strip() for p in doc]
    if any(t for t in native_texts):
        full_text = "\n\n".join(native_texts)
        doc.close()
        did = _save_as_document(file_path, full_text, fmt="pdf_text")
        return {"status": "success", "doc_id": did, "pages": page_count, "method": "pdf_text"}

    # ── Scanned PDF: render pages as images → OCR ──
    try:
        from core.harness.infrastructure.infra_ocr_adapter import create_infra_ocr_adapter
        ocr = create_infra_ocr_adapter()
    except Exception:
        ocr = None

    with _tempfile.TemporaryDirectory() as tmpdir:
        texts = []
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=200)
            img_path = _os.path.join(tmpdir, f"p{i:04d}.png")
            pix.save(img_path)
            try:
                t = ocr.ocr_frame(img_path) if ocr else ""
            except Exception:
                t = ""
            texts.append(t.strip())
        doc.close()
        full_text = "\n\n".join(texts)

    did = _save_as_document(file_path, full_text or "[scanned_pdf_no_text]", fmt="ocr")
    return {"status": "success", "doc_id": did, "pages": page_count, "method": "ocr"}


def _inject_csv(file_path: str) -> dict:
    import pandas as pd
    df = pd.read_csv(file_path)
    text = df.to_string(max_rows=500)
    doc_id = _save_as_document(file_path, text, fmt="csv")
    return {"status": "success", "doc_id": doc_id, "rows": len(df), "method": "csv_parse"}


def _inject_excel(file_path: str) -> dict:
    import pandas as pd
    xls = pd.ExcelFile(file_path)
    total = 0
    first_doc = ""
    for sheet in xls.sheet_names:
        df = pd.read_excel(file_path, sheet_name=sheet)
        text = df.to_string(max_rows=500)
        did = _save_as_document(file_path, text, fmt=f"excel/{sheet}")
        first_doc = first_doc or did
        total += len(df)
    return {"status": "success", "doc_id": first_doc or "", "rows": total,
            "sheets": len(xls.sheet_names), "method": "excel_parse"}


def _inject_text(file_path: str) -> dict:
    with open(file_path, encoding="utf-8", errors="ignore") as f:
        text = f.read()[:50000]
    doc_id = _save_as_document(file_path, text, fmt="text")
    return {"status": "success", "doc_id": doc_id, "chars": len(text), "method": "text_parse"}


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    files = params.get("file_paths") or []
    results: List[dict] = []
    errors: List[str] = []
    total_records = 0

    for fp in files:
        if not os.path.exists(fp):
            errors.append(f"文件不存在: {fp}")
            continue
        ext = Path(fp).suffix.lower()
        handler_key = _HANDLERS.get(ext)
        if not handler_key:
            errors.append(f"不支持格式: {ext} ({fp})")
            continue

        try:
            if handler_key == "pdf":
                r = _inject_pdf(fp)
                total_records += r.get("pages", 0)
            elif handler_key == "csv":
                r = _inject_csv(fp)
                total_records += r.get("rows", 0)
            elif handler_key == "excel":
                r = _inject_excel(fp)
                total_records += r.get("rows", 0)
            else:
                r = _inject_text(fp)
                total_records += r.get("chars", 0)
            results.append(r)
        except Exception as e:
            errors.append(f"{os.path.basename(fp)}: {e}")

    return {
        "status": "partial" if errors else "success",
        "total_files": len(files),
        "records": total_records,
        "results": results,
        "errors": errors,
    }
