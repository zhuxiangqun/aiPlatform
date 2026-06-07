from __future__ import annotations

import hashlib
import os
import re
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.utils.ids import new_prefixed_id

from .db import KBSqlite
from .storage import get_tenant_storage

# Reuse PoC pipeline for now (A 阶段先收敛为技能/存储；后续可替换为 MinerU/Docling/自研结构化)
from .poc.ingest import ingest_scanned_pdf
from .poc.mineru_extract import (
    extract_tables_from_content_list,
    load_mineru_content_list,
    run_mineru_parse,
)
from .intelligence.embeddings import embed_text
from core.api.facades.kb_facade import kb_parse_document, kb_chunk_document
from core.api.facades.kb_facade import kb_classify_document


def _safe_readable_path(p: str) -> bool:
    # Basic safety: must be absolute and exist.
    try:
        pp = Path(p).expanduser()
        return pp.is_absolute() and pp.exists()
    except Exception:
        return False


def _stable_doc_id(file_path: str) -> str:
    try:
        sha = hashlib.sha256(Path(file_path).read_bytes()).hexdigest()[:12]
        return f"doc_{sha}"
    except Exception:
        return new_prefixed_id("doc")


def enqueue_ingest(
    *,
    tenant_id: str,
    collection_id: str,
    file_path: str,
    kind: str = "pdf",
    ocr_lang: str = "zh",
    ocr_engine: Optional[str] = None,
    dpi: int = 240,
    max_pages: Optional[int] = 60,
    name: str = "",
) -> Dict[str, Any]:
    """
    异步入库：创建 doc + job，后台线程执行 ingest_document。
    返回 {job_id, doc_id} 供前端轮询。
    """
    if not tenant_id:
        raise ValueError("tenant_id_required")
    if not collection_id:
        raise ValueError("collection_id_required")
    if not file_path:
        raise ValueError("file_path_required")
    if not _safe_readable_path(file_path):
        raise ValueError("file_path_not_accessible")

    st = get_tenant_storage(tenant_id)
    db = KBSqlite(st.db_path)
    db.ensure_schema()
    db.upsert_collection(tenant_id=st.tenant_id, collection_id=collection_id, name=name)

    doc_id = _stable_doc_id(file_path)
    job_id = new_prefixed_id("job")

    db.upsert_document(
        tenant_id=st.tenant_id,
        doc_id=doc_id,
        collection_id=collection_id,
        source_uri=file_path,
        kind=kind,
        status="queued",
        meta={"ocr_lang": ocr_lang, "ocr_engine": ocr_engine, "dpi": dpi, "max_pages": max_pages, "last_job_id": job_id},
    )
    db.create_job(
        tenant_id=st.tenant_id,
        job_id=job_id,
        type="ingest",
        collection_id=collection_id,
        doc_id=doc_id,
        status="queued",
        progress=0.0,
        message="queued",
        input={
            "tenant_id": tenant_id,
            "collection_id": collection_id,
            "file_path": file_path,
            "kind": kind,
            "ocr_lang": ocr_lang,
            "ocr_engine": ocr_engine,
            "dpi": dpi,
            "max_pages": max_pages,
        },
    )
    db.append_job_event(tenant_id=st.tenant_id, job_id=job_id, level="info", message="queued", extra={})

    def _runner() -> None:
        db2 = KBSqlite(st.db_path)
        last_evt_ts = 0.0
        last_evt_msg = ""

        def progress_cb(progress: float, message: str, extra: Dict[str, Any]) -> None:
            nonlocal last_evt_ts, last_evt_msg
            # clamp
            try:
                p = float(progress)
            except Exception:
                p = None
            if p is not None:
                if p < 0:
                    p = 0.0
                if p > 0.99:
                    p = 0.99
            db2.update_job(tenant_id=st.tenant_id, job_id=job_id, progress=p, message=message)
            now = time.time()
            # throttle event writes: at most 1 per 1s or on message change
            if message != last_evt_msg or (now - last_evt_ts) >= 1.0:
                last_evt_ts = now
                last_evt_msg = message
                db2.append_job_event(tenant_id=st.tenant_id, job_id=job_id, level="info", message=message, extra=extra or {})

        try:
            db2.update_job(tenant_id=st.tenant_id, job_id=job_id, status="running", progress=0.01, message="start")
            db2.append_job_event(tenant_id=st.tenant_id, job_id=job_id, level="info", message="start", extra={})
            # mark doc running
            db2.upsert_document(
                tenant_id=st.tenant_id,
                doc_id=doc_id,
                collection_id=collection_id,
                source_uri=file_path,
                kind=kind,
                status="ingesting",
                meta={"ocr_lang": ocr_lang, "ocr_engine": ocr_engine, "dpi": dpi, "max_pages": max_pages, "last_job_id": job_id},
            )
            out = ingest_document(
                tenant_id=tenant_id,
                collection_id=collection_id,
                file_path=file_path,
                kind=kind,
                ocr_lang=ocr_lang,
                ocr_engine=ocr_engine,
                dpi=dpi,
                max_pages=max_pages,
                name=name,
                progress_cb=progress_cb,
                last_job_id=job_id,
            )
            db2.update_job(
                tenant_id=st.tenant_id,
                job_id=job_id,
                status="completed",
                progress=1.0,
                message="completed",
                output=out,
            )
            db2.append_job_event(tenant_id=st.tenant_id, job_id=job_id, level="info", message="completed", extra={})
        except Exception as e:
            db2.update_job(
                tenant_id=st.tenant_id,
                job_id=job_id,
                status="failed",
                progress=1.0,
                message=str(e),
                error={"code": "EXCEPTION", "message": str(e)},
            )
            db2.append_job_event(
                tenant_id=st.tenant_id,
                job_id=job_id,
                level="error",
                message="failed",
                extra={"error": str(e)},
            )

    t = threading.Thread(target=_runner, name=f"kb_ingest_{job_id}", daemon=True)
    t.start()

    return {"tenant_id": st.tenant_id, "collection_id": collection_id, "job_id": job_id, "doc_id": doc_id}


def enqueue_directory_ingest(
    *,
    tenant_id: str,
    collection_id: str,
    directory: str,
    recursive: bool = True,
    pattern: str = "*.md",
    kind: str = "markdown",
    name: str = "",
) -> Dict[str, Any]:
    """
    批量导入目录中匹配的文件。
    返回 {job_ids: [...], doc_ids: [...], total: N}。
    """
    if not tenant_id:
        raise ValueError("tenant_id_required")
    if not collection_id:
        raise ValueError("collection_id_required")
    if not directory:
        raise ValueError("directory_required")

    target_dir = Path(directory).expanduser()
    if not target_dir.is_dir():
        raise ValueError(f"Directory not found or not accessible: {directory}")

    # Scan current files + compute doc_ids
    current_docs: Dict[str, str] = {}  # file_path → doc_id
    for fpath in sorted(target_dir.glob(pattern)):
        if not recursive and fpath.parent != target_dir:
            continue
        fp = str(fpath)
        current_docs[fp] = _stable_doc_id(fp)

    # Clean up stale docs: files deleted or content changed
    stale_cleaned = 0
    st = get_tenant_storage(tenant_id)
    db = KBSqlite(st.db_path)
    db.ensure_schema()
    try:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT doc_id, source_uri FROM documents WHERE tenant_id=? AND collection_id=?",
                (tenant_id, collection_id),
            ).fetchall()
            for r in rows:
                existing_uri = r["source_uri"]
                existing_doc = r["doc_id"]
                should_clean = False
                if isinstance(existing_uri, str) and existing_uri not in current_docs:
                    should_clean = True  # File deleted
                elif isinstance(existing_uri, str) and current_docs.get(existing_uri, "") != existing_doc:
                    should_clean = True  # Content changed
                if should_clean:
                    try:
                        conn.execute("DELETE FROM documents WHERE tenant_id=? AND doc_id=?", (tenant_id, existing_doc))
                        conn.execute("DELETE FROM kb_elements WHERE tenant_id=? AND doc_id=?", (tenant_id, existing_doc))
                        conn.execute("DELETE FROM kb_embeddings WHERE tenant_id=? AND doc_id=?", (tenant_id, existing_doc))
                        stale_cleaned += 1
                    except Exception:
                        pass
            conn.commit()
    except Exception:
        pass

    job_ids = []
    doc_ids = []
    skipped = 0
    cleaned = len(current_docs) - len(doc_ids) if len(doc_ids) < len(current_docs) else 0

    for fp in sorted(current_docs.keys()):
        try:
            result = enqueue_ingest(
                tenant_id=tenant_id,
                collection_id=collection_id,
                file_path=fp,
                kind=kind,
                name=name,
            )
            job_ids.append(result["job_id"])
            doc_ids.append(result["doc_id"])
        except ValueError:
            skipped += 1
            continue

    return {
        "tenant_id": tenant_id,
        "collection_id": collection_id,
        "job_ids": job_ids,
        "doc_ids": doc_ids,
        "total": len(doc_ids),
        "skipped": skipped,
        "cleaned": stale_cleaned,
    }


def ingest_document(
    *,
    tenant_id: str,
    collection_id: str,
    file_path: str,
    kind: str = "pdf",
    ocr_lang: str = "zh",
    ocr_engine: Optional[str] = None,
    dpi: int = 240,
    max_pages: Optional[int] = 60,
    name: str = "",
    progress_cb: Optional[Callable[[float, str, Dict[str, Any]], None]] = None,
    last_job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ingest 单文档（目前实现：扫描 PDF → OCR → 预算表结构化 → 入库）。
    返回 doc_id 与入库摘要。
    """
    if not tenant_id:
        raise ValueError("tenant_id_required")
    if not collection_id:
        raise ValueError("collection_id_required")
    if not file_path:
        raise ValueError("file_path_required")
    if not _safe_readable_path(file_path):
        raise ValueError("file_path_not_accessible")

    if str(kind or "").lower() == "video":
        from .video import ingest_video_document

        return ingest_video_document(
            tenant_id=tenant_id,
            collection_id=collection_id,
            file_path=file_path,
            kind="video",
            name=name,
            progress_cb=progress_cb,
            last_job_id=last_job_id,
        )

    # ── Text-based formats (word/ppt/markdown) ──
    _kind_lower = str(kind or "").lower()
    if _kind_lower in ("word", "docx", "ppt", "pptx", "md", "markdown", "xlsx", "xls", "csv", "pdf", "audio", "mp3", "wav", "image", "png", "jpg", "json", "txt", "text", "plain"):
        effective_kind = _kind_lower
        parsed = kb_parse_document(file_path, _kind_lower)
        if _kind_lower in ("word", "docx"):
            effective_kind = "word"
        elif _kind_lower in ("pdf",):
            effective_kind = "pdf"
        elif _kind_lower in ("ppt", "pptx"):
            effective_kind = "ppt"
        elif _kind_lower in ("xlsx", "xls"):
            effective_kind = "xlsx"
        elif _kind_lower == "csv":
            effective_kind = "csv"
        elif _kind_lower in ("audio", "mp3", "wav"):
            effective_kind = "audio"
        elif _kind_lower in ("image", "png", "jpg"):
            effective_kind = "image"
        elif _kind_lower == "json":
            effective_kind = "json"
        elif _kind_lower in ("txt", "text", "plain"):
            effective_kind = "txt"
        else:
            effective_kind = "markdown"

        st = get_tenant_storage(tenant_id)
        db = KBSqlite(st.db_path)
        db.ensure_schema()
        db.upsert_collection(tenant_id=st.tenant_id, collection_id=collection_id, name=name)

        doc_id = _stable_doc_id(file_path)
        try:
            db.archive_doc_data(tenant_id=st.tenant_id, doc_id=doc_id)
        except Exception:
            pass
        db.upsert_document(
            tenant_id=st.tenant_id,
            doc_id=doc_id,
            collection_id=collection_id,
            source_uri=file_path,
            kind=effective_kind,
            status="ingesting",
            meta={"last_job_id": last_job_id, "parser": effective_kind},
        )

        if progress_cb:
            progress_cb(0.1, "parsed", {"format": effective_kind, "elements": len(parsed)})

        # ── Auto-select chunking strategy based on document features ──
        from core.api.facades.kb_facade import kb_chunk_elements

        try:
            raw_chunks = kb_chunk_elements(parsed, kind=effective_kind, target_size=1000, overlap=150)
            if raw_chunks:
                chunked = []
                for ch in raw_chunks:
                    chunked.append({
                        "type": "text",
                        "text": ch["text"],
                        "page_idx": ch.get("page_idx", 0),
                        "meta": ch.get("meta", {}),
                    })
                parsed = chunked
        except Exception:
            pass

        for i, el in enumerate(parsed):
            element_id = new_prefixed_id("el")
            el_text = str(el.get("text") or "")[:20000]
            db.insert_element(
                tenant_id=st.tenant_id,
                element_id=element_id,
                doc_id=doc_id,
                type=str(el.get("type") or "text"),
                page_idx=int(el.get("page_idx") or 0),
                bbox=None,
                text=el_text,
                cells=el.get("cells") or None,
                asset_id=None,
                meta=el.get("meta") or {},
            )
            db.insert_embedding(
                tenant_id=st.tenant_id,
                embedding_id=new_prefixed_id("emb"),
                doc_id=doc_id,
                element_id=element_id,
                embedding_type=str(el.get("type") or "text"),
                vector=embed_text(el_text[:4000]),
                model="hash-128",
            )
            if progress_cb and len(parsed) > 1:
                progress_cb(0.1 + 0.85 * (i + 1) / len(parsed), "embedding", {"i": i, "total": len(parsed)})

        cls_result = kb_classify_document(parsed, effective_kind)

        db.upsert_document(
            tenant_id=st.tenant_id,
            doc_id=doc_id,
            collection_id=collection_id,
            source_uri=file_path,
            kind=effective_kind,
            status="ready",
            meta={
                "last_job_id": last_job_id,
                "parser": effective_kind,
                "pages": len(parsed),
                "elements": len(parsed),
                "classification": cls_result,
            },
        )

        return {
            "doc_id": doc_id,
            "pages": len(parsed),
            "elements": len(parsed),
            "assets_dir": "",
        }

    st = get_tenant_storage(tenant_id)
    db = KBSqlite(st.db_path)
    db.ensure_schema()
    db.upsert_collection(tenant_id=st.tenant_id, collection_id=collection_id, name=name)

    doc_id = _stable_doc_id(file_path)
    # Clean previous ingest artifacts for idempotent re-ingest of same file/doc_id.
    try:
        db.delete_doc_data(tenant_id=st.tenant_id, doc_id=doc_id)
    except Exception:
        pass
    db.upsert_document(
        tenant_id=st.tenant_id,
        doc_id=doc_id,
        collection_id=collection_id,
        source_uri=file_path,
        kind=kind,
        status="ingesting",
        meta={
            "ocr_lang": ocr_lang,
            "ocr_engine": ocr_engine,
            "dpi": dpi,
            "max_pages": max_pages,
            "last_job_id": last_job_id,
        },
    )

    # Work dir under tenant assets (persisted)
    out_dir = Path(st.assets_dir) / doc_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- P1(A): try MinerU first (structure-driven table extraction) ---
    mineru_rows: List[Tuple[int, Dict[str, Any]]] = []
    mineru_tables: List[Dict[str, Any]] = []
    try:
        use_mineru = os.getenv("AIPLAT_KB_PARSER", "auto").lower() in ("auto", "mineru")
        if progress_cb:
            progress_cb(0.06, "mineru_gate", {"AIPLAT_KB_PARSER": os.getenv("AIPLAT_KB_PARSER"), "enabled": use_mineru})
        if use_mineru:
            if progress_cb:
                progress_cb(0.08, "mineru_parse_start", {})
            mineru_out_dir = run_mineru_parse(
                pdf_path=file_path,
                out_dir=str(out_dir / "mineru"),
                max_pages=max_pages,
                parse_method="auto",
                heartbeat_cb=lambda elapsed, timeout_s, extra: (
                    progress_cb(
                        0.08,
                        "mineru_parsing",
                        {"elapsed_s": int(elapsed), "timeout_s": int(timeout_s), **(extra or {})},
                    )
                    if progress_cb
                    else None
                ),
            )
            content_list = load_mineru_content_list(str(mineru_out_dir))
            mineru_tables = extract_tables_from_content_list(content_list)

            def _cells_to_budget_rows(cells: List[List[str]]) -> List[Dict[str, Any]]:
                if not cells or len(cells) < 2:
                    return []
                header = [str(c).strip() for c in cells[0]]

                def _find_col(keys: List[str]) -> Optional[int]:
                    for i, h in enumerate(header):
                        for k in keys:
                            if k in h:
                                return i
                    return None

                item_ci = _find_col(["预算科目", "科目", "项目", "内容"])
                y2026_ci = _find_col(["2026"])
                y2027_ci = _find_col(["2027"])
                total_ci = _find_col(["合计", "总计"])
                if item_ci is None or y2026_ci is None:
                    return []

                def _to_amount(x: str) -> Optional[float]:
                    import re

                    s = (x or "").replace(",", "").strip()
                    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
                    if not m:
                        return None
                    try:
                        return float(m.group(0))
                    except Exception:
                        return None

                out_rows: List[Dict[str, Any]] = []
                for r in cells[1:]:
                    if not isinstance(r, list) or item_ci >= len(r):
                        continue
                    item = str(r[item_ci]).strip()
                    if not item:
                        continue
                    y2026_v = _to_amount(str(r[y2026_ci])) if y2026_ci < len(r) else None
                    y2027_v = _to_amount(str(r[y2027_ci])) if (y2027_ci is not None and y2027_ci < len(r)) else None
                    total_v = _to_amount(str(r[total_ci])) if (total_ci is not None and total_ci < len(r)) else None
                    if y2026_v is None and y2027_v is None and total_v is None:
                        continue
                    out_rows.append(
                        {
                            "item": item,
                            "y2026": y2026_v,
                            "y2027": y2027_v,
                            "total": total_v,
                            "cells": {
                                "item": {"text": item, "bbox": None},
                                "y2026": {"text": str(r[y2026_ci]) if y2026_ci < len(r) else "", "bbox": None},
                                "y2027": {"text": str(r[y2027_ci]) if (y2027_ci is not None and y2027_ci < len(r)) else "", "bbox": None},
                                "total": {"text": str(r[total_ci]) if (total_ci is not None and total_ci < len(r)) else "", "bbox": None},
                            },
                        }
                    )
                return out_rows

            for t in mineru_tables:
                page_idx = int(t.get("page_idx") or 0)
                cells = t.get("cells") or []
                for rr in _cells_to_budget_rows(cells):
                    mineru_rows.append((page_idx, rr))

            if progress_cb:
                progress_cb(0.18, "mineru_parse_done", {"tables": len(mineru_tables), "budget_rows": len(mineru_rows)})
    except Exception as e:
        if progress_cb:
            progress_cb(0.18, "mineru_parse_failed", {"error": str(e)})
        mineru_rows = []
        mineru_tables = []

    try:
        res = ingest_scanned_pdf(
            file_path,
            out_dir=str(out_dir),
            dpi=int(dpi),
            max_pages=int(max_pages) if max_pages else None,
            ocr_lang=ocr_lang,
            ocr_engine=ocr_engine,
            progress_cb=progress_cb,
        )
    except Exception as e:
        # Ensure UI can see failure state instead of forever "ingesting".
        db.upsert_document(
            tenant_id=st.tenant_id,
            doc_id=doc_id,
            collection_id=collection_id,
            source_uri=file_path,
            kind=kind,
            status="failed",
            meta={
                "error": str(e),
                "ocr_lang": ocr_lang,
                "ocr_engine": ocr_engine,
                "dpi": dpi,
                "max_pages": max_pages,
                "last_job_id": last_job_id,
            },
        )
        raise

    # Register page images as assets
    if progress_cb:
        progress_cb(0.94, "persist_assets", {"pages": len(res.page_images)})
    for page_idx, img_path in enumerate(res.page_images):
        asset_id = f"{doc_id}_page_{page_idx:04d}"
        db.insert_asset(
            tenant_id=st.tenant_id,
            asset_id=asset_id,
            doc_id=doc_id,
            kind="page_image",
            local_path=str(img_path),
            page_idx=page_idx,
            meta={},
        )

    # Persist generic elements for later doc_query/doc_summarize.
    # Minimal: store per-page OCR text and detected tables (if any).
    if progress_cb:
        progress_cb(0.955, "persist_elements", {})

    def _tokens_to_text(tokens: List[Any]) -> str:
        # tokens are OCRToken with .text and .bbox
        if not tokens:
            return ""
        # sort by y then x
        def cy(t):
            b = getattr(t, "bbox", None) or [0, 0, 0, 0]
            return (float(b[1]) + float(b[3])) / 2.0

        def cx(t):
            b = getattr(t, "bbox", None) or [0, 0, 0, 0]
            return (float(b[0]) + float(b[2])) / 2.0

        ts = sorted(tokens, key=lambda t: (cy(t), cx(t)))
        # adaptive tol
        y_tol = 12
        lines: List[List[Any]] = []
        cur: List[Any] = []
        cur_y: Optional[float] = None
        for t in ts:
            y = cy(t)
            if cur_y is None or abs(y - cur_y) <= y_tol:
                cur.append(t)
                cur_y = y if cur_y is None else (cur_y * 0.7 + y * 0.3)
            else:
                lines.append(cur)
                cur = [t]
                cur_y = y
        if cur:
            lines.append(cur)
        out_lines: List[str] = []
        for ln in lines:
            ln2 = sorted(ln, key=cx)
            parts: List[str] = []
            for tok in ln2:
                s = str(getattr(tok, "text", "") or "").strip()
                if not s:
                    continue
                if not parts:
                    parts.append(s)
                else:
                    # Insert a space between alnum sequences; keep CJK tight.
                    prev = parts[-1]
                    if re.fullmatch(r"[A-Za-z0-9.]+", prev[-1:]) and re.fullmatch(r"[A-Za-z0-9.]+", s[:1]):
                        parts.append(" " + s)
                    else:
                        parts.append(s)
            out_lines.append("".join(parts).strip())
        text = "\n".join([x for x in out_lines if x])
        # Keep size bounded for SQLite/debug.
        return text[:20000]

    # 1) Per-page text elements from OCR tokens.
    for page_idx, toks in enumerate(res.ocr_by_page or []):
        text = _tokens_to_text(toks or [])
        if not text.strip():
            continue
        element_id = new_prefixed_id("el")
        db.insert_element(
            tenant_id=st.tenant_id,
            element_id=element_id,
            doc_id=doc_id,
            type="text",
            page_idx=int(page_idx),
            bbox=None,
            text=text,
            cells=None,
            asset_id=None,
            meta={"source": "ocr"},
        )
        db.insert_embedding(
            tenant_id=st.tenant_id,
            embedding_id=new_prefixed_id("emb"),
            doc_id=doc_id,
            element_id=element_id,
            embedding_type="text",
            vector=embed_text(text[:4000]),
            model="hash-128",
        )

    # 2) Table elements: prefer MinerU tables when available; fallback to OCR-extracted budget rows.
    if mineru_tables:
        for t in mineru_tables:
            db.insert_element(
                tenant_id=st.tenant_id,
                element_id=new_prefixed_id("el"),
                doc_id=doc_id,
                type="table",
                page_idx=int(t.get("page_idx") or 0),
                bbox=None,
                text="\n".join([str(x) for x in (t.get("caption") or [])])[:2000] if isinstance(t.get("caption"), list) else None,
                cells=t.get("cells") or None,
                asset_id=None,
                meta={"source": "mineru", "caption": t.get("caption") or []},
            )
    elif res.tables_by_page:
        for page_idx, table in enumerate(res.tables_by_page):
            if not table:
                continue
            rows = []
            for r in table:
                rows.append(
                    {
                        "item": r.get("item"),
                        "y2026": r.get("y2026"),
                        "y2027": r.get("y2027"),
                        "total": r.get("total"),
                    }
                )
            db.insert_element(
                tenant_id=st.tenant_id,
                element_id=new_prefixed_id("el"),
                doc_id=doc_id,
                type="table",
                page_idx=int(page_idx),
                bbox=None,
                text="budget_rows",
                cells=rows,
                asset_id=None,
                meta={"source": "ocr_budget_extract"},
            )

    # Persist budget table rows (structured)
    if progress_cb:
        progress_cb(0.97, "persist_budget_rows", {})
    rows_written = 0
    table_pages = []
    if mineru_rows:
        for page_idx, r in mineru_rows:
            item = str(r.get("item") or "").strip()
            if not item:
                continue
            row_id = new_prefixed_id("kbrow")
            db.insert_budget_row(
                tenant_id=st.tenant_id,
                row_id=row_id,
                doc_id=doc_id,
                page_idx=int(page_idx),
                item=item,
                y2026=r.get("y2026"),
                y2027=r.get("y2027"),
                total=r.get("total"),
                cells=r.get("cells") or {},
            )
            rows_written += 1
            if int(page_idx) not in table_pages:
                table_pages.append(int(page_idx))
        table_pages.sort()
    elif res.tables_by_page:
        for page_idx, table in enumerate(res.tables_by_page):
            if not table:
                continue
            table_pages.append(page_idx)
            for r in table:
                item = str(r.get("item") or "").strip()
                if not item:
                    continue
                row_id = new_prefixed_id("kbrow")
                db.insert_budget_row(
                    tenant_id=st.tenant_id,
                    row_id=row_id,
                    doc_id=doc_id,
                    page_idx=page_idx,
                    item=item,
                    y2026=r.get("y2026"),
                    y2027=r.get("y2027"),
                    total=r.get("total"),
                    cells=r.get("cells") or {},
                )
                rows_written += 1

    # Build elements snapshot for classification
    _cls_elements = []
    for page_idx, toks in enumerate(res.ocr_by_page or []):
        _text = _tokens_to_text(toks or [])
        if _text.strip():
            _cls_elements.append({"type": "text", "text": _text, "page_idx": page_idx, "cells": None,
                                   "meta": {"source": "ocr"}})
    for t in (mineru_tables or res.tables_by_page or []):
        _t_text = "\n".join(str(x) for x in (t.get("caption") or [])) if isinstance(t.get("caption"), list) else str(t.get("caption", ""))
        _cls_elements.append({"type": "table", "text": _t_text, "page_idx": int(t.get("page_idx", 0)),
                               "cells": t.get("cells"), "meta": {"source": "mineru" if mineru_tables else "ocr"}})
    cls_result = kb_classify_document(_cls_elements, kind)

    db.upsert_document(
        tenant_id=st.tenant_id,
        doc_id=doc_id,
        collection_id=collection_id,
        source_uri=file_path,
        kind=kind,
        status="ready",
        meta={
            "pages": len(res.page_images),
            "budget_rows": rows_written,
            "budget_pages": table_pages,
            "ocr_lang": ocr_lang,
            "ocr_engine": ocr_engine,
            "dpi": dpi,
            "max_pages": max_pages,
            "last_job_id": last_job_id,
            "classification": cls_result,
        },
    )

    return {
        "tenant_id": st.tenant_id,
        "collection_id": collection_id,
        "doc_id": doc_id,
        "pages": len(res.page_images),
        "budget_rows": rows_written,
        "budget_pages": table_pages,
        "assets_dir": str(out_dir),
    }


def load_doc_kinds(*, tenant_id: str, doc_ids: List[str]) -> List[str]:
    """Load document 'kind' metadata for a list of document IDs.
    
    Lives in the service layer (allowed to use KBSqlite). Agents should call
    this function instead of directly accessing KBSqlite (violates §5.9).
    """
    if not doc_ids:
        return []
    try:
        from .storage import get_tenant_storage
        st = get_tenant_storage(tenant_id)
        db = KBSqlite(st.db_path)
        db.ensure_schema()
        with db.connect() as conn:
            placeholders = ",".join(["?"] * len(doc_ids))
            rows = conn.execute(
                f"SELECT doc_id, kind FROM documents WHERE tenant_id=? AND doc_id IN ({placeholders})",
                (tenant_id, *doc_ids),
            ).fetchall()
        return [str(dict(r).get("kind") or "").strip().lower() for r in rows if str(dict(r).get("kind") or "").strip()]
    except Exception:
        return []


def _format_transcript_with_punctuation(segments: list) -> str:
    """Build punctuated transcript out of whisper segments.

    Zero-cost approach:
    - Segments with timing gap > 0.6s get period + new paragraph
    - Segments with timing gap > 0.15s get period
    - Otherwise insert commas between segments (whisper VAD removes natural pauses)
    - Every ~5 consecutive commas → replace with period for readability
    """
    if not segments:
        return ""
    lines: list = []
    prev_end = None
    consecutive_commas = 0
    for seg in segments:
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        start_s = (seg.get("start_ms", 0) or 0) / 1000.0
        end_s = (seg.get("end_ms", 0) or 0) / 1000.0

        if prev_end is not None:
            gap = start_s - prev_end
            if gap > 0.6:
                lines.append("。\n\n")
                consecutive_commas = 0
                lines.append(text)  # no comma after period
                prev_end = end_s
                continue
            elif gap > 0.15:
                lines.append("。")
                consecutive_commas = 0
            elif consecutive_commas >= 8:
                lines.append("。")
                consecutive_commas = 0
            else:
                lines.append("，")
                consecutive_commas += 1
        lines.append(text)
        prev_end = end_s
    if lines:
        lines.append("。")
    return "".join(lines)


def preview_document(
    *,
    file_path: str,
    kind: str = "pdf",
    max_elements: int = 500,
) -> Dict[str, Any]:
    """
    Parse a document without saving to KB — returns text preview + classification.
    Callers use this to show users what will be ingested before they confirm.
    """
    if not file_path:
        raise ValueError("file_path_required")
    if not _safe_readable_path(file_path):
        raise ValueError("file_path_not_accessible")

    k = str(kind or "").lower()
    elements: List[Dict[str, Any]] = []
    parser = ""

    if k in ("word", "docx"):
        elements = kb_parse_document(file_path, "word")
        parser = "docx"
    elif k in ("pdf",):
        elements = kb_parse_document(file_path, "pdf")
        parser = "pdf"
    elif k in ("ppt", "pptx"):
        elements = kb_parse_document(file_path, "ppt")
        parser = "pptx"
    elif k in ("xlsx", "xls"):
        elements = kb_parse_document(file_path, "xlsx")
        parser = "xlsx"
    elif k == "csv":
        elements = kb_parse_document(file_path, "csv")
        parser = "csv"
    elif k in ("md", "markdown"):
        elements = kb_parse_document(file_path, "markdown")
        parser = "markdown"
    elif k in ("txt", "text", "plain"):
        text = Path(file_path).read_text(encoding="utf-8", errors="replace")
        elements = [{"type": "paragraph", "text": text[:10000], "page": 1}]
        parser = "text"
    elif k in ("audio", "mp3", "wav", "m4a"):
        elements = kb_parse_document(file_path, "audio")
        parser = "audio"
    elif k in ("image", "png", "jpg", "jpeg", "bmp"):
        elements = kb_parse_document(file_path, "image")
        parser = "image"
    elif k in ("json",):
        elements = kb_parse_document(file_path, "json")
        parser = "json"
    elif k == "video":
        # Extract audio from video file and transcribe via core/harness transcriber
        import subprocess, tempfile, os as _os, json as _json
        from core.api.facades.kb_facade import kb_transcribe_audio as _transcribe_audio
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            audio_path = tmp.name
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", file_path, "-vn", "-acodec", "pcm_s16le",
                 "-ar", "16000", "-ac", "1", audio_path],
                check=True, capture_output=True, timeout=120,
            )
            segments = _transcribe_audio(audio_path, language="zh")
            full_text = _format_transcript_with_punctuation(segments)
            if full_text:
                elements = [{"type": "paragraph", "text": full_text[:80000], "page": 1}]
            else:
                elements = [{"type": "paragraph", "text": "(no speech detected)", "page": 1}]
            parser = "whisper"
            for seg in segments[:max_elements]:
                seg_text = str(seg.get("text", ""))
                if seg_text.strip():
                    elements.append({
                        "type": "text",
                        "text": seg_text,
                        "page": len(elements),
                        "meta": {
                            "source": "video_transcript",
                            "start_s": round((seg.get("start_ms", 0) or 0) / 1000, 1),
                            "end_s": round((seg.get("end_ms", 0) or 0) / 1000, 1),
                        },
                    })

            # ── Cache parsed results so ingest can skip re-parsing ──
            try:
                cache = {
                    "kind": "video",
                    "parser": parser,
                    "segments": [
                        {"text": str(s.get("text", "")), "start_ms": int(s.get("start_ms", 0) or 0),
                         "end_ms": int(s.get("end_ms", 0) or 0)}
                        for s in segments
                    ],
                }
                cache_path = file_path + ".preview_cache.json"
                _os.makedirs(_os.path.dirname(cache_path) or ".", exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as f:
                    _json.dump(cache, f, ensure_ascii=False)
            except Exception:
                pass
        finally:
            try:
                _os.unlink(audio_path)
            except OSError:
                pass
    else:
        # PDF: use PoC OCR pipeline for first few pages
        import tempfile
        from .poc.ingest import ingest_scanned_pdf
        with tempfile.TemporaryDirectory() as tmpdir:
            res = ingest_scanned_pdf(
                pdf_path=file_path, out_dir=tmpdir, ocr_lang="zh",
                ocr_engine=os.getenv("AIPLAT_KB_OCR_ENGINE", "tesseract"),
                dpi=150, max_pages=3,
            )
            parser = "ocr"
            for page_idx, toks in enumerate(res.ocr_by_page or []):
                # Inline token-to-text conversion (from ingest_document)
                if not toks:
                    continue
                lines: List[List[Any]] = []
                cur: List[Any] = []
                cur_y: Optional[float] = None
                for t in sorted(toks, key=lambda t: ((getattr(t, "bbox", [0,0,0,0])[1] + getattr(t, "bbox", [0,0,0,0])[3]) / 2)):
                    y = (getattr(t, "bbox", [0,0,0,0])[1] + getattr(t, "bbox", [0,0,0,0])[3]) / 2
                    if cur_y is None or abs(y - cur_y) <= 12:
                        cur.append(t)
                        cur_y = y if cur_y is None else (cur_y * 0.7 + y * 0.3)
                    else:
                        lines.append(cur)
                        cur = [t]
                        cur_y = y
                if cur:
                    lines.append(cur)
                out_parts: List[str] = []
                for ln in lines:
                    parts = [str(getattr(tok, "text", "") or "").strip() for tok in sorted(ln, key=lambda t: (getattr(t, "bbox", [0,0,0,0])[0] + getattr(t, "bbox", [0,0,0,0])[2]) / 2)]
                    out_parts.append("".join(parts))
                text = "\n".join(out_parts)[:2000]
                if text.strip():
                    elements.append({
                        "type": "text", "text": text,
                        "page_idx": page_idx,
                        "meta": {"source": "ocr"},
                    })

    elements = elements[:max_elements]
    # Deduplicate and enrich
    seen: set = set()
    enriched: list = []
    for e in elements:
        t = str(e.get("text", ""))
        key = (e.get("type"), t[:80])
        if key not in seen:
            seen.add(key)
            enriched.append(e)
    elements = enriched[:max_elements]
    classification = kb_classify_document(elements, kind) if elements else {}

    return {
        "file_path": file_path,
        "kind": kind,
        "parser": parser,
        "elements": [
            {"text": str(e.get("text", "")), "type": e.get("type", "text"),
             "page_idx": e.get("page_idx"), "meta": e.get("meta")}
            for e in elements
        ],
        "element_count": len(elements),
        "classification": classification,
    }


# ── Directory Watch / Auto-Sync ──

_WATCH_THREADS: Dict[str, threading.Thread] = {}
_WATCH_STOP_FLAGS: Dict[str, bool] = {}


def watch_directory(
    *, tenant_id: str, watch_id: str, directory: str,
    collection_id: str = "default", recursive: bool = True,
    pattern: str = "*.md", kind: str = "markdown", poll_interval: float = 30.0,
) -> Dict[str, Any]:
    """Start background watcher for a directory. On each poll, ingest new/changed files."""
    if watch_id in _WATCH_THREADS:
        unwatch_directory(tenant_id=tenant_id, watch_id=watch_id)

    st = get_tenant_storage(tenant_id)
    db = KBSqlite(st.db_path)
    db.ensure_schema()

    db.upsert_watch(
        tenant_id=tenant_id, watch_id=watch_id,
        directory_path=directory, collection_id=collection_id,
        recursive=recursive, pattern=pattern, enabled=True,
    )

    _WATCH_STOP_FLAGS[watch_id] = False

    def _poll():
        while not _WATCH_STOP_FLAGS.get(watch_id, True):
            try:
                result = enqueue_directory_ingest(
                    tenant_id=tenant_id, collection_id=collection_id,
                    directory=directory, recursive=recursive, pattern=pattern, kind=kind,
                )
                if result.get("total", 0) > 0:
                    try:
                        db.touch_watch(tenant_id=tenant_id, watch_id=watch_id)
                    except Exception:
                        pass
            except Exception:
                pass
            time.sleep(max(poll_interval, 5.0))

    t = threading.Thread(target=_poll, name=f"kb_watch_{watch_id}", daemon=True)
    t.start()
    _WATCH_THREADS[watch_id] = t

    return {"status": "watching", "watch_id": watch_id, "directory": directory}


def unwatch_directory(*, tenant_id: str, watch_id: str) -> Dict[str, Any]:
    """Stop a directory watcher."""
    _WATCH_STOP_FLAGS[watch_id] = True
    t = _WATCH_THREADS.pop(watch_id, None)
    if t:
        t.join(timeout=2.0)
    try:
        st = get_tenant_storage(tenant_id)
        KBSqlite(st.db_path).delete_watch(tenant_id=tenant_id, watch_id=watch_id)
    except Exception:
        pass
    return {"status": "unwatched", "watch_id": watch_id}


def list_watches(*, tenant_id: str) -> List[Dict[str, Any]]:
    """List active directory watches."""
    try:
        st = get_tenant_storage(tenant_id)
        return KBSqlite(st.db_path).list_watches(tenant_id=tenant_id, enabled_only=False)
    except Exception:
        return []


# ── Vault Browser ──

def _resolve_doc_source(tenant_id: str, doc_id: str) -> Optional[str]:
    """Get source_uri for a document from the KB."""
    try:
        st = get_tenant_storage(tenant_id)
        with KBSqlite(st.db_path).connect() as conn:
            row = conn.execute(
                "SELECT source_uri FROM documents WHERE tenant_id=? AND doc_id=?",
                (tenant_id, doc_id),
            ).fetchone()
            return row["source_uri"] if row else None
    except Exception:
        return None


def vault_connect(
    *, tenant_id: str, vault_path: str, label: str = "", auto_index: bool = True,
) -> Dict[str, Any]:
    """Connect a local directory as a vault (read-only browsing, no copy)."""
    target = Path(vault_path).expanduser()
    if not target.is_dir():
        raise ValueError(f"Directory not found: {vault_path}")
    vault_id = hashlib.md5(str(target).encode()).hexdigest()[:12]

    st = get_tenant_storage(tenant_id)
    KBSqlite(st.db_path).ensure_schema()
    KBSqlite(st.db_path).upsert_vault(
        tenant_id=tenant_id, vault_id=vault_id,
        vault_path=str(target), label=label, auto_index=auto_index,
    )
    return {"vault_id": vault_id, "vault_path": str(target), "status": "connected"}


def vault_disconnect(*, tenant_id: str, vault_id: str) -> Dict[str, Any]:
    """Disconnect a vault."""
    KBSqlite(get_tenant_storage(tenant_id).db_path).delete_vault(tenant_id=tenant_id, vault_id=vault_id)
    return {"vault_id": vault_id, "status": "disconnected"}


def vault_list(*, tenant_id: str) -> List[Dict[str, Any]]:
    """List connected vaults."""
    try:
        vaults = KBSqlite(get_tenant_storage(tenant_id).db_path).list_vaults(tenant_id=tenant_id)
        # ③ Disconnect detection: check if vault path still exists
        for v in vaults:
            v["path_exists"] = Path(v.get("vault_path", "")).expanduser().is_dir()
        return vaults
    except Exception:
        return []


def vault_tree(*, vault_path: str, subdir: str = "", max_depth: int = 3,
               vault_id: str = "", tenant_id: str = "default") -> Dict[str, Any]:
    """Return directory tree for a vault starting from subdir. Includes wiki status per file."""
    root = Path(vault_path).expanduser()
    if not root.is_dir():
        raise ValueError(f"Directory not found: {vault_path}")
    if subdir:
        root = root / subdir.lstrip("/")
        if not root.is_dir():
            raise ValueError(f"Subdirectory not found: {subdir}")

    file_statuses = {}
    if vault_id:
        try:
            db = KBSqlite(get_tenant_storage(tenant_id).db_path)
            db.ensure_schema()
            file_statuses = db.get_vault_file_statuses(vault_id=vault_id)
        except Exception:
            pass

    def _walk(path: Path, depth: int) -> List[Dict[str, Any]]:
        if depth > max_depth:
            return []
        entries = []
        try:
            for entry in sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
                if entry.name.startswith("."):
                    continue
                if entry.is_file() and entry.suffix in (".md", ".markdown"):
                    file_path_str = str(entry)
                    status = file_statuses.get(file_path_str, "ready")
                    entries.append({
                        "name": entry.name,
                        "path": file_path_str,
                        "type": "file",
                        "size": entry.stat().st_size,
                        "status": status,
                    })
                elif entry.is_dir():
                    children = _walk(entry, depth + 1)
                    entries.append({
                        "name": entry.name,
                        "path": str(entry),
                        "type": "directory",
                        "children": children,
                    })
        except PermissionError:
            pass
        return entries

    return {"vault_path": str(root), "subdir": subdir, "entries": _walk(root, 0)}


def vault_read(*, file_path: str) -> Dict[str, Any]:
    """Read a markdown file from the vault and return content + frontmatter."""
    p = Path(file_path).expanduser()
    if not p.is_file():
        raise ValueError(f"File not found: {file_path}")
    content = p.read_text(encoding="utf-8", errors="ignore")
    frontmatter = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                import yaml as _yaml
                fm = _yaml.safe_load(parts[1]) or {}
                if isinstance(fm, dict):
                    frontmatter = dict(fm)
            except Exception:
                pass
            body = parts[2]
    return {
        "file_path": str(p),
        "name": p.name,
        "frontmatter": frontmatter,
        "content": body.strip(),
        "raw": content,
    }


async def vault_to_wiki(*, file_path: str, label: str = "", collection_id: str = "",
                       vault_id: str = "", tenant_id: str = "default") -> Dict[str, Any]:
    """Convert a vault markdown file to a Wiki page using the full KB pipeline.

    collection_id: derived from subdirectory name for auto-collection mapping.
    vault_id: if provided, record file status in kb_vault_files after conversion.
    """
    from core.api.core_facade import wiki_auto_update

    p = Path(file_path).expanduser()
    if not p.is_file():
        raise ValueError(f"File not found: {file_path}")

    # Compute stable doc_id from file content hash
    doc_id = _stable_doc_id(str(p))

    try:
        # Run the full wiki pipeline (parse→chunk→embed→LLM curate→knowledge atoms)
        result = await wiki_auto_update(doc_id=doc_id, file_path=str(p), collection_id=collection_id)

        status = result.get("status", "created")
        category = result.get("category", "")
        title = result.get("title", p.stem)

        if status in ("created", "skipped") and vault_id:
            try:
                db = KBSqlite(get_tenant_storage(tenant_id).db_path)
                db.ensure_schema()
                db.upsert_vault_file(
                    vault_id=vault_id, file_path=str(p), doc_id=doc_id,
                )
            except Exception:
                pass

        # V1: Schema validation after conversion
        schema_ok = None
        try:
            from core.harness.knowledge.wiki_engine import read_page
            from core.harness.knowledge.knowledge_ontology import validate_page_against_schema
            saved = read_page(title, collection_id=collection_id, category=category)
            if saved:
                val = validate_page_against_schema(saved, collection_id=collection_id, mode="warning")
                schema_ok = val.is_valid
        except Exception:
            pass

        return {
            "status": status,
            "title": title,
            "category": category,
            "chars": result.get("chars", 0),
            "doc_id": doc_id,
            "schema_valid": schema_ok,
        }
    except Exception as e:
        # Record failed status for observability
        if vault_id:
            try:
                db = KBSqlite(get_tenant_storage(tenant_id).db_path)
                db.ensure_schema()
                db.upsert_vault_file_failed(
                    vault_id=vault_id, file_path=str(p), error=str(e)[:200],
                )
            except Exception:
                pass
        raise


# ── Vault Indexer ──

_VAULT_INDEX_THREADS: Dict[str, threading.Thread] = {}
_VAULT_INDEX_STOP: Dict[str, bool] = {}
_VAULT_INDEX_STATE: Dict[str, Dict[str, Any]] = {}  # vault_id → {status, progress, last_error}


def vault_start_indexer(
    *, tenant_id: str, vault_id: str, vault_path: str,
    collection_id: str = "default", poll_interval: float = 30.0,
    auto_wiki: bool = False,
) -> Dict[str, Any]:
    """Start background indexer for a vault. Optionally auto-wiki new files."""
    key = f"{tenant_id}:{vault_id}"
    if key in _VAULT_INDEX_THREADS:
        vault_stop_indexer(tenant_id=tenant_id, vault_id=vault_id)

    _VAULT_INDEX_STOP[key] = False
    _VAULT_INDEX_STATE[key] = {"status": "running", "progress": 0, "cleaned": 0, "wikified": 0, "last_error": None}

    def _poll():
        while not _VAULT_INDEX_STOP.get(key, True):
            try:
                vault_dir = Path(vault_path).expanduser()
                if not vault_dir.is_dir():
                    _VAULT_INDEX_STATE[key] = {"status": "error", "progress": -1, "last_error": f"Vault path not found: {vault_path}"}
                    return

                # Scan vault files directly (no documents table pollution)
                md_files = sorted(vault_dir.rglob("*.md"))
                total = len(md_files)
                wikified = 0

                # Auto-wiki: send newly detected files to Wiki directly
                if auto_wiki and total > 0:
                    for fpath in md_files:
                        try:
                            if fpath.name.startswith("."):
                                continue
                            file_path_str = str(fpath)
                            import asyncio as _asyncio
                            loop = _asyncio.new_event_loop()
                            try:
                                result = loop.run_until_complete(
                                    vault_to_wiki(file_path=file_path_str,
                                                  collection_id=collection_id,
                                                  vault_id=vault_id,
                                                  tenant_id=tenant_id))
                                if result.get("status") in ("created", "skipped"):
                                    wikified += 1
                            finally:
                                loop.close()
                        except Exception:
                            pass

                _VAULT_INDEX_STATE[key] = {
                    "status": "running",
                    "progress": total,
                    "cleaned": 0,
                    "wikified": wikified,
                    "last_error": None,
                }
                if total > 0 or wikified > 0:
                    try:
                        KBSqlite(get_tenant_storage(tenant_id).db_path).touch_vault(
                            tenant_id=tenant_id, vault_id=vault_id,
                        )
                    except Exception:
                        pass
            except Exception as e:
                _VAULT_INDEX_STATE[key] = {"status": "error", "progress": -1, "last_error": str(e)}
            time.sleep(max(poll_interval, 5.0))

    t = threading.Thread(target=_poll, name=f"vault_index_{vault_id}", daemon=True)
    t.start()
    _VAULT_INDEX_THREADS[key] = t

    return {"status": "indexing", "vault_id": vault_id}


def vault_stop_indexer(*, tenant_id: str, vault_id: str) -> Dict[str, Any]:
    """Stop vault indexer."""
    key = f"{tenant_id}:{vault_id}"
    _VAULT_INDEX_STOP[key] = True
    t = _VAULT_INDEX_THREADS.pop(key, None)
    if t:
        t.join(timeout=2.0)
    _VAULT_INDEX_STATE.pop(key, None)
    return {"status": "stopped", "vault_id": vault_id}


def vault_index_status(*, tenant_id: str, vault_id: str) -> Dict[str, Any]:
    """Get indexer status."""
    key = f"{tenant_id}:{vault_id}"
    return _VAULT_INDEX_STATE.get(key, {"status": "idle", "progress": 0, "last_error": None})


def vault_reindex(*, tenant_id: str, vault_path: str, collection_id: str = "default") -> Dict[str, Any]:
    """Rebuild all indexes for a vault: clear existing docs + re-scan + re-ingest."""
    st = get_tenant_storage(tenant_id)
    db = KBSqlite(st.db_path)
    db.ensure_schema()

    # Clear existing docs from this vault (matching source_uri prefix)
    try:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT doc_id FROM documents WHERE tenant_id=? AND source_uri LIKE ?",
                (tenant_id, f"{vault_path}%"),
            ).fetchall()
            for r in rows:
                did = r["doc_id"]
                conn.execute("DELETE FROM documents WHERE tenant_id=? AND doc_id=?", (tenant_id, did))
                conn.execute("DELETE FROM kb_elements WHERE tenant_id=? AND doc_id=?", (tenant_id, did))
                conn.execute("DELETE FROM kb_embeddings WHERE tenant_id=? AND doc_id=?", (tenant_id, did))
            conn.commit()
            cleared = len(rows)
    except Exception as e:
        cleared = 0

    result = enqueue_directory_ingest(
        tenant_id=tenant_id, collection_id=collection_id,
        directory=vault_path, recursive=True, pattern="*.md", kind="markdown",
    )
    return {
        "status": "reindexing",
        "cleared": cleared,
        "queued": result.get("total", 0),
        "job_ids": result.get("job_ids", []),
    }
