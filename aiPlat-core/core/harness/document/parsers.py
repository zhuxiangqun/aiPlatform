"""
Core document parsers — unified document format → text elements.

Each parser takes a file path and returns a list of element dicts:
  {type: "text"|"table", text: str, page_idx: int, cells: Optional[List], meta: dict}

Callers:
  - platform/kb/service.py (ingest pipeline)
  - Any AI agent that needs to read documents before reasoning
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List


def _fallback_text(file_path: str, source: str) -> List[Dict[str, Any]]:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    if not text.strip():
        return []
    return [{"type": "text", "text": text.strip(), "page_idx": 0, "cells": None, "meta": {"source": source, "fallback": True}}]


# ── DOCX ──

def parse_docx(file_path: str) -> List[Dict[str, Any]]:
    try: from docx import Document
    except ImportError: return _fallback_text(file_path, "docx")
    doc = Document(file_path)
    elements: List[Dict[str, Any]] = []
    for para in doc.paragraphs:
        text = (para.text or "").strip()
        if not text: continue
        elements.append({"type": "text", "text": text, "page_idx": 0, "cells": None, "meta": {"source": "docx"}})
    for ti, table in enumerate(doc.tables):
        rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        if any(any(c for c in row) for row in rows):
            elements.append({"type": "table", "text": "\n".join(" | ".join(r) for r in rows), "page_idx": 0, "cells": rows, "meta": {"source": "docx", "table_index": ti}})
    return elements or _fallback_text(file_path, "docx")


# ── PPTX ──

def parse_pptx(file_path: str) -> List[Dict[str, Any]]:
    try: from pptx import Presentation
    except ImportError: return _fallback_text(file_path, "pptx")
    prs = Presentation(file_path)
    elements: List[Dict[str, Any]] = []
    for si, slide in enumerate(prs.slides):
        texts = [para.text.strip() for shape in slide.shapes if shape.has_text_frame for para in shape.text_frame.paragraphs if (para.text or "").strip()]
        if texts: elements.append({"type": "text", "text": "\n".join(texts), "page_idx": si, "cells": None, "meta": {"source": "pptx", "slide_index": si}})
    return elements or _fallback_text(file_path, "pptx")


# ── MARKDOWN ──

def parse_markdown(file_path: str) -> List[Dict[str, Any]]:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    if not text.strip(): return []

    # Extract YAML frontmatter (Obsidian-style --- at top)
    frontmatter: Dict[str, Any] = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                import yaml as _yaml
                fm = _yaml.safe_load(parts[1]) or {}
                if isinstance(fm, dict):
                    frontmatter = {k: fm[k] for k in fm}
            except Exception:
                pass
            body = parts[2]

    # Extract [[wikilinks]]
    wikilinks = re.findall(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", body)
    link_texts = [l[0] for l in wikilinks]

    # Split body by markdown headings
    sections = re.split(r"\n(?=#{1,6}\s)", body)
    elements: List[Dict[str, Any]] = []
    for si, section in enumerate(sections):
        if section.strip():
            meta = {"source": "markdown"}
            # First section inherits full frontmatter; later sections get summary
            if frontmatter:
                meta.update(frontmatter if si == 0 else {
                    "tags": frontmatter.get("tags", []) if isinstance(frontmatter.get("tags"), list) else [],
                    "aliases": frontmatter.get("aliases", []) if isinstance(frontmatter.get("aliases"), list) else [],
                })
            if link_texts:
                meta["wikilinks"] = link_texts
            elements.append({
                "type": "text", "text": section.strip(),
                "page_idx": si, "cells": None, "meta": meta,
            })
    return elements or [{
        "type": "text", "text": text.strip(), "page_idx": 0, "cells": None,
        "meta": {"source": "markdown", **frontmatter},
    }]


# ── XLSX ──

def parse_xlsx(file_path: str) -> List[Dict[str, Any]]:
    try: from openpyxl import load_workbook
    except ImportError: return _fallback_text(file_path, "xlsx")
    wb = load_workbook(file_path, read_only=True, data_only=True)
    elements: List[Dict[str, Any]] = []
    for si, sheet_name in enumerate(wb.sheetnames):
        ws = wb[sheet_name]
        rows = [[str(c).strip() if c is not None else "" for c in row] for row in ws.iter_rows(values_only=True) if any(c is not None for c in row)]
        if rows:
            elements.append({"type": "table", "text": "\n".join(" | ".join(r) for r in rows), "page_idx": si, "cells": rows, "meta": {"source": "xlsx", "sheet_name": sheet_name}})
    wb.close()
    return elements or _fallback_text(file_path, "xlsx")


# ── CSV ──

def parse_csv(file_path: str) -> List[Dict[str, Any]]:
    import csv
    content = None
    for enc in ("utf-8", "utf-8-sig", "latin-1", "gbk"):
        try:
            with open(file_path, "r", encoding=enc, errors="replace") as f: content = f.read()
            break
        except Exception: continue
    if content is None: return []
    rows = [[c.strip() for c in row] for row in csv.reader(content.splitlines())]
    if not rows: return []
    texts = [" | ".join(r) for r in rows]
    return [{"type": "table", "text": "\n".join(texts), "page_idx": 0, "cells": rows, "meta": {"source": "csv", "rows": len(rows)}}]


# ── PDF ──

def parse_pdf(file_path: str) -> List[Dict[str, Any]]:
    elements: List[Dict[str, Any]] = []
    try:
        import fitz
        doc = fitz.open(file_path)
        for pi in range(len(doc)):
            text = doc[pi].get_text().strip()
            if text: elements.append({"type": "text", "text": text, "page_idx": pi, "cells": None, "meta": {"source": "pdf", "engine": "pymupdf"}})
        doc.close()
        if elements: return elements
    except ImportError: pass
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            for pi, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text and text.strip(): elements.append({"type": "text", "text": text.strip(), "page_idx": pi, "cells": None, "meta": {"source": "pdf", "engine": "pdfplumber"}})
        if elements: return elements
    except ImportError: pass
    return elements or _fallback_text(file_path, "pdf")


# ── MarkItDown (unified DOCX/PPTX/XLSX/PDF/HTML → structured Markdown) ──

def parse_markitdown(file_path: str) -> List[Dict[str, Any]]:
    """Convert office documents to structured Markdown via MarkItDown, then split by headings.

    Preserves heading hierarchy (#/##/###), tables (Markdown tables), lists, and links.
    Falls back to format-specific parser if MarkItDown is unavailable.
    """
    ext = os.path.splitext(file_path)[1].lower().lstrip(".")
    if ext == "html":
        return _parse_markitdown_impl(file_path, ext)
    try:
        from markitdown import MarkItDown
    except ImportError:
        return _fallback_text(file_path, f"markitdown+{ext}")
    return _parse_markitdown_impl(file_path, ext)


def _parse_markitdown_impl(file_path: str, ext: str) -> List[Dict[str, Any]]:
    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(file_path)
        text = result.text_content or ""
    except Exception as e:
        return [{"type": "text", "text": f"[markitdown conversion failed: {e}]",
                 "page_idx": 0, "cells": None, "meta": {"source": f"markitdown+{ext}", "error": str(e)}}]

    if not text.strip():
        return []

    # Split by Markdown headings (reuse same strategy as parse_markdown)
    sections = re.split(r"\n(?=#{1,6}\s)", text)
    elements: List[Dict[str, Any]] = []
    for si, section in enumerate(sections):
        if section.strip():
            elements.append({
                "type": "text",
                "text": section.strip(),
                "page_idx": si,
                "cells": None,
                "meta": {"source": f"markitdown+{ext}", "parser": "markitdown"},
            })
    return elements or [{
        "type": "text", "text": text.strip(), "page_idx": 0, "cells": None,
        "meta": {"source": f"markitdown+{ext}", "parser": "markitdown"},
    }]


# ── HTML (via MarkItDown) ──

def parse_html(file_path: str) -> List[Dict[str, Any]]:
    """Parse HTML files via MarkItDown → structured Markdown."""
    return parse_markitdown(file_path)


# ── Audio ──

def parse_audio(file_path: str) -> List[Dict[str, Any]]:
    ext = os.path.splitext(file_path)[1].lower().strip(".")
    if ext not in ("mp3", "wav", "m4a", "ogg", "flac", "aac", "opus", "wma"):
        return [{"type": "text", "text": f"[unsupported audio format: .{ext}]", "page_idx": 0, "cells": None, "meta": {"source": "audio", "error": "unsupported_format"}}]
    try:
        from core.harness.document.transcriber import transcribe_audio
        segments = transcribe_audio(file_path, language="zh")
        text = " ".join(s.get("text", "") for s in segments if s.get("text"))
        return [{"type": "text", "text": text, "page_idx": 0, "cells": None, "meta": {"source": "audio"}}] if text else [{"type": "text", "text": "[no speech detected]", "page_idx": 0, "cells": None, "meta": {"source": "audio"}}]
    except Exception as e:
        return [{"type": "text", "text": f"[audio transcription failed: {e}]", "page_idx": 0, "cells": None, "meta": {"source": "audio", "error": str(e)}}]


# ── Image ──

def parse_image(file_path: str) -> List[Dict[str, Any]]:
    ext = os.path.splitext(file_path)[1].lower().strip(".")
    if ext not in ("png", "jpg", "jpeg", "bmp", "tiff", "tif", "webp"):
        return [{"type": "text", "text": f"[unsupported image format: .{ext}]", "page_idx": 0, "cells": None, "meta": {"source": "image", "error": "unsupported_format"}}]
    try:
        from core.harness.document.ocr import ocr_keyframes
        segments = ocr_keyframes([file_path])
        text = " ".join(s.get("text", "") for s in segments if s.get("text"))
        return [{"type": "text", "text": text, "page_idx": 0, "cells": None, "meta": {"source": "image"}}] if text else [{"type": "text", "text": "[no text detected]", "page_idx": 0, "cells": None, "meta": {"source": "image"}}]
    except Exception as e:
        return [{"type": "text", "text": f"[image OCR failed: {e}]", "page_idx": 0, "cells": None, "meta": {"source": "image", "error": str(e)}}]


# ── JSON ──

def parse_json_document(file_path: str) -> List[Dict[str, Any]]:
    import json as _json
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f: data = _json.load(f)
        if isinstance(data, list): text = "\n".join(_json.dumps(item, ensure_ascii=False) for item in data[:200])
        elif isinstance(data, dict): text = _json.dumps(data, ensure_ascii=False, indent=2)
        else: text = str(data)
        return [{"type": "text", "text": text, "page_idx": 0, "cells": None, "meta": {"source": "json"}}]
    except Exception as e:
        return [{"type": "text", "text": f"[json parse failed: {e}]", "page_idx": 0, "cells": None, "meta": {"source": "json", "error": str(e)}}]


# ── Email .eml ──

def parse_eml(file_path: str) -> List[Dict[str, Any]]:
    import email
    from email.policy import default
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f: msg = email.message_from_string(f.read(), policy=default)
        parts = [f"Subject: {msg.get('Subject', '(no subject)')}", f"From: {msg.get('From', '(unknown)')}", f"Date: {msg.get('Date', '(unknown)')}"]
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload: body += payload.decode("utf-8", errors="replace") + "\n"
        else:
            payload = msg.get_payload(decode=True)
            if payload: body = payload.decode("utf-8", errors="replace")
        if body.strip(): parts.append(f"\nBody:\n{body.strip()}")
        return [{"type": "text", "text": "\n".join(parts), "page_idx": 0, "cells": None, "meta": {"source": "eml"}}]
    except Exception as e:
        return [{"type": "text", "text": f"[email parse failed: {e}]", "page_idx": 0, "cells": None, "meta": {"source": "eml", "error": str(e)}}]


__all__ = ["parse_docx", "parse_pptx", "parse_markdown", "parse_xlsx", "parse_csv", "parse_pdf", "parse_audio", "parse_image", "parse_json_document", "parse_eml", "parse_markitdown", "parse_html", "extract_images_from_document", "describe_images"]


# ── Image extraction from documents ──

def extract_images_from_document(file_path: str, output_dir: str = None) -> List[str]:
    """Extract embedded images from DOCX/PDF/PPTX to a temp directory."""
    import tempfile
    ext = os.path.splitext(file_path)[1].lower()
    out = output_dir or tempfile.mkdtemp(prefix="aiplat_img_")
    os.makedirs(out, exist_ok=True)
    extracted: List[str] = []

    if ext in (".docx", ".doc"):
        extracted = _extract_docx_images(file_path, out)
    elif ext == ".pdf":
        extracted = _extract_pdf_images(file_path, out)
    elif ext in (".pptx", ".ppt"):
        extracted = _extract_pptx_images(file_path, out)
    return extracted


def _extract_docx_images(file_path: str, out_dir: str) -> List[str]:
    extracted = []
    try:
        from docx import Document
        doc = Document(file_path)
        for i, rel in enumerate(doc.part.rels.values()):
            if "image" in rel.reltype:
                img_data = rel.target_part.blob
                ext2 = os.path.splitext(rel.target_part.partname)[1] or ".png"
                img_path = os.path.join(out_dir, f"docx_img_{i}{ext2}")
                with open(img_path, "wb") as f:
                    f.write(img_data)
                extracted.append(img_path)
    except ImportError:
        pass
    return extracted


def _extract_pdf_images(file_path: str, out_dir: str) -> List[str]:
    extracted = []
    try:
        import fitz
        doc = fitz.open(file_path)
        for pi in range(len(doc)):
            for img_info in doc[pi].get_images(full=True):
                xref = img_info[0]
                base_img = doc.extract_image(xref)
                img_bytes = base_img["image"]
                ext2 = base_img.get("ext", "png")
                img_path = os.path.join(out_dir, f"pdf_p{pi}_img_{xref}.{ext2}")
                with open(img_path, "wb") as f:
                    f.write(img_bytes)
                extracted.append(img_path)
        doc.close()
    except ImportError:
        pass
    return extracted


def _extract_pptx_images(file_path: str, out_dir: str) -> List[str]:
    extracted = []
    try:
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE
        prs = Presentation(file_path)
        for si, slide in enumerate(prs.slides):
            for shape in slide.shapes:
                if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                    img = shape.image
                    ct = img.content_type or "image/png"
                    ext2 = ct.split("/")[-1] if "/" in ct else "png"
                    img_path = os.path.join(out_dir, f"pptx_s{si}_{shape.shape_id}.{ext2}")
                    with open(img_path, "wb") as f:
                        f.write(img.blob)
                    extracted.append(img_path)
    except ImportError:
        pass
    return extracted


# ── Image description via infra LLM vision ──

async def describe_images(image_paths: List[str],
                           model_name: str = None,
                           prompt: str = "请用2-3句中文描述这张图片的主要内容，包括图中展示的结构、流程或关键信息。") -> List[Dict[str, str]]:
    """Generate semantic descriptions for images using a vision-capable LLM."""
    results = []
    if not image_paths:
        return results

    import base64

    try:
        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
        if not model_name:
            model_name = best_model_for_purpose("vision") or best_model_for_purpose("multimodal")
        if not model_name:
            model_name = (os.getenv("AIPLAT_VISION_MODEL") or
                         os.getenv("AIPLAT_LLM_MODEL") or "")
        if not model_name:
            return [{"path": p, "description": "", "error": "no vision model configured"}
                    for p in image_paths]
        adapter = create_selected_adapter(model_name=model_name)
    except Exception:
        return [{"path": p, "description": "", "error": "model init failed"}
                for p in image_paths]

    for img_path in image_paths[:8]:
        try:
            with open(img_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")
            ext3 = os.path.splitext(img_path)[1].lower().strip(".")
            mime = f"image/{ext3}" if ext3 in ("png", "jpeg", "jpg", "gif", "webp") else "image/png"
            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
                ]
            }]
            resp = await adapter.generate(messages, config=None)
            desc = resp.content if hasattr(resp, 'content') else str(resp)
            results.append({"path": img_path, "description": desc.strip(), "error": None})
        except Exception as e:
            results.append({"path": img_path, "description": "", "error": str(e)[:200]})

    return results
