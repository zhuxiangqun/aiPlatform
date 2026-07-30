from __future__ import annotations

import asyncio
import hashlib
import logging
import os

logger = logging.getLogger(__name__)
import re
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.utils.ids import new_prefixed_id

from .db import KBSqlite
from .storage import get_tenant_storage

# PR B: MinerU now integrated into core PdfConverter chain — use CoreFacade
from .poc.ingest import ingest_scanned_pdf
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
                    except Exception as e:
                        logging.debug(str(e), exc_info=True)
            conn.commit()
    except Exception as e:
        logging.debug(str(e), exc_info=True)

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




def ingest_url(
    *,
    tenant_id: str,
    collection_id: str,
    url: str,
    name: str = "",
    kind: str = "html",
) -> Dict[str, Any]:
    """Ingest a web page by URL — fetch, parse HTML, ingest as document."""
    if not url:
        raise ValueError("url_required")
    if not tenant_id:
        raise ValueError("tenant_id_required")

    import tempfile, re, asyncio
    import httpx

    async def _fetch():
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "aiPlat-RAG/1.0"})
            r.raise_for_status()
            return r.text

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                html_text = pool.submit(asyncio.run, _fetch()).result(timeout=30)
        else:
            html_text = asyncio.run(_fetch())
    except RuntimeError:
        html_text = asyncio.run(_fetch())

    # Parse HTML to plain text
    try:
        from core.api.core_facade import parse_html as _parse_html  # v2.5: CoreFacade
        text = _parse_html(html_text)
    except (ImportError, AttributeError):
        text = re.sub(r"<[^>]+>", " ", html_text)
        text = re.sub(r"\s+", " ", text).strip()

    if not text or len(text) < 50:
        raise ValueError(f"URL returned insufficient content: {len(text)} chars")

    doc_name = name or url.rsplit("/", 1)[-1][:60] or "web_page"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as tmp:
        tmp.write(text)
        tmp_path = tmp.name

    try:
        return ingest_document(
            tenant_id=tenant_id, collection_id=collection_id,
            file_path=tmp_path, kind=kind, name=doc_name,
        )
    finally:
        try:
            __import__("os").unlink(tmp_path)
        except Exception:
            logging.getLogger(__name__).debug('_fetch failed', exc_info=True)



def _cells_to_budget_rows(cells: List[List[str]]) -> List[Dict[str, Any]]:
    """Extract budget rows from 2D table cells (consumes DocumentElement.cells).

    Matches columns: 预算科目/科目/项目/内容, 2026, 2027, 合计/总计.
    Platform business logic — no dependency on parser source.
    """
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
        out_rows.append({
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
        })
    return out_rows


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

    # Phase G: Document metadata governance check
    _doc_meta = {"ingested_at": time.time()}
    if os.getenv("AIPLAT_KB_STRICT_META", "").lower() in ("true", "1"):
        if not name:
            raise ValueError("document name is required in strict metadata mode (AIPLAT_KB_STRICT_META=true)")

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

    # Phase D: content hash change detection — skip unchanged documents
    import hashlib
    doc_id = hashlib.md5(f"{tenant_id}:{collection_id}:{file_path}".encode()).hexdigest()[:16] if not name else name
    try:
        raw_bytes = open(file_path, "rb").read()
        import re as _re
        normalized = _re.sub(rb"\s+", b" ", raw_bytes)
        new_hash = hashlib.sha256(normalized).hexdigest()
        st = get_tenant_storage(tenant_id)
        db_path = os.path.join(str(st), "aiplat_knowledge.sqlite3")
        if os.path.exists(db_path):
            import sqlite3
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    "SELECT content_hash FROM documents WHERE tenant_id=? AND doc_id=?",
                    (tenant_id, doc_id),
                ).fetchone()
                if row and row[0] == new_hash:
                    conn.close()
                    logger.info("content_hash unchanged for doc_id=%s — skip re-ingest", doc_id)
                    return {"doc_id": doc_id, "status": "skipped_unchanged", "content_hash": new_hash}
            finally:
                conn.close()
    except Exception:
        new_hash = ""

    # ── Text-based formats ──
    from core.api.facades.kb_facade import _KIND_TO_EXT, normalize_kind
    _kind_lower = str(kind or "").lower()
    if _kind_lower in _KIND_TO_EXT or _kind_lower in ("txt", "text", "plain"):
        effective_kind = normalize_kind(_kind_lower)
        parsed = kb_parse_document(file_path, _kind_lower)

        st = get_tenant_storage(tenant_id)
        db = KBSqlite(st.db_path)
        db.ensure_schema()
        db.upsert_collection(tenant_id=st.tenant_id, collection_id=collection_id, name=name)

        doc_id = _stable_doc_id(file_path)
        try:
            db.archive_doc_data(tenant_id=st.tenant_id, doc_id=doc_id)
        except Exception as e:
            logging.debug(str(e), exc_info=True)
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
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        for i, el in enumerate(parsed):
            element_id = new_prefixed_id("el")
            el_text = _mask_pii(str(el.get("text") or "")[:20000])
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
    except Exception as e:
        logging.debug(str(e), exc_info=True)
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

    # --- P1(A): CoreFacade unified parse (PdfConverter with MinerU Tier 3) ---
    mineru_rows: List[Tuple[int, Dict[str, Any]]] = []
    mineru_tables: List[Dict[str, Any]] = []
    try:
        use_mineru = os.getenv(
            "AIPLAT_PDF_MINERU_ENABLED",
            os.getenv("AIPLAT_KB_PARSER", "auto"),
        ).strip().lower() in ("auto", "mineru", "true", "1")
        if progress_cb:
            progress_cb(0.06, "kb_parse_start", {"parser": "core_facade"})
        if use_mineru:
            if progress_cb:
                progress_cb(0.08, "kb_parse_core", {})
            elements = kb_parse_document(file_path, kind="pdf")
            mineru_tables = [
                {"page_idx": e.page_idx, "cells": e.cells, "caption": []}
                for e in elements if e.type == "table"
            ]
            for t in mineru_tables:
                page_idx = int(t.get("page_idx") or 0)
                cells = t.get("cells") or []
                for rr in _cells_to_budget_rows(cells):
                    mineru_rows.append((page_idx, rr))
            if progress_cb:
                progress_cb(0.18, "kb_parse_done",
                            {"tables": len(mineru_tables), "budget_rows": len(mineru_rows)})
    except Exception as e:
        if progress_cb:
            progress_cb(0.18, "kb_parse_failed", {"error": str(e)})
        mineru_rows = []
        mineru_tables = []

    # Phase B: OCR pipeline (page images + per-page text)
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


def _mask_pii(text: str) -> str:
    """Mask PII in text before storing in KB. Safe fallback on import error."""
    try:
        from core.api.core_facade import get_pii_detector  # v2.5: canonical path
        masked, _ = get_pii_detector().mask(text)
        return masked
    except Exception:
        return text


def _format_transcript_with_punctuation(segments: list) -> str:
    """Build punctuated transcript out of whisper segments.

    Zero-cost approach:
    - Segments with timing gap > 0.6s get period + new paragraph
    - Segments with timing gap > 0.15s get period
    - Otherwise insert commas between segments (whisper VAD removes natural pauses)
    - Every 8 consecutive commas → replace with period for readability
    - Every 150 chars+3 segments or 300+ chars without a paragraph break → force break
    - Total chars since last break ≥ 500 → force paragraph even if gap is small
    """
    if not segments:
        return ""
    lines: list = []
    prev_end = None
    consecutive_commas = 0
    chars_since_break = 0
    segments_since_break = 0
    for seg in segments:
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        start_s = (seg.get("start_ms", 0) or 0) / 1000.0
        end_s = (seg.get("end_ms", 0) or 0) / 1000.0

        if prev_end is not None:
            gap = start_s - prev_end
            force_break = (chars_since_break > 150 and segments_since_break >= 3) or chars_since_break >= 300
            if gap > 0.6 or force_break:
                if consecutive_commas > 0:
                    lines[-1] = lines[-1].rstrip("，") + "。"
                lines.append("\n\n")
                consecutive_commas = 0
                chars_since_break = 0
                segments_since_break = 0
                lines.append(text)
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
        chars_since_break += len(text)
        segments_since_break += 1
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
    diags: Dict[str, Any] = {}

    from core.api.facades.kb_facade import _KIND_TO_EXT, normalize_kind
    canonical = normalize_kind(k)
    if k in _KIND_TO_EXT:
        elements = kb_parse_document(file_path, k)
        parser = canonical
    elif k in ("txt", "text", "plain"):
        text = _mask_pii(Path(file_path).read_text(encoding="utf-8", errors="replace"))
        elements = [{"type": "paragraph", "text": text[:10000], "page": 1}]
        parser = "text"
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
                check=True, capture_output=True, timeout=600,
            )

            # Probe extracted audio duration for coverage diagnostics
            audio_dur_ms = 0
            try:
                from core.api.core_facade import probe_duration_ms  # v2.5: CoreFacade
                audio_dur_ms = probe_duration_ms(audio_path)
            except Exception as e:
                logging.debug(str(e), exc_info=True)

            diags.clear()
            segments = _transcribe_audio(audio_path, language="zh", diagnostics=diags)

            # Coverage ratio: how much of the audio Whisper captured
            if audio_dur_ms > 0 and diags.get("last_end_ms", 0) > 0:
                diags["audio_duration_ms"] = audio_dur_ms
                diags["coverage_ratio"] = round(min(diags["last_end_ms"] / audio_dur_ms, 1.0), 3)
            else:
                diags["audio_duration_ms"] = audio_dur_ms
                diags["coverage_ratio"] = 1.0

            # Chunked fallback when coverage is low (likely ffmpeg timeout or Whisper crash)
            if diags.get("coverage_ratio", 1.0) < 0.5:
                try:
                    from core.api.facades.kb_facade import kb_transcribe_audio_chunked
                    segments = kb_transcribe_audio_chunked(audio_path, language="zh")
                    diags["fallback_used"] = "chunked"
                    if audio_dur_ms > 0 and segments:
                        diags["coverage_ratio"] = round(
                            min(segments[-1]["end_ms"] / audio_dur_ms, 1.0), 3)
                except Exception:
                    diags["fallback_error"] = "chunked_transcription_failed"

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
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        finally:
            try:
                _os.unlink(audio_path)
            except OSError as e:
                logging.debug(str(e), exc_info=True)
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

    result: Dict[str, Any] = {
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
    if diags:
        result["diagnostics"] = diags
    return result


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
                    except Exception as e:
                        logging.debug(str(e), exc_info=True)
                    # PR: Auto-update Wiki pages after reingest
                    for doc_id in result.get("doc_ids", [])[:10]:
                        try:
                            import asyncio as _aio
                            from core.api.core_facade import wiki_auto_update
                            file_path = None
                            for fp, did in result.get("_path_map", {}).items():
                                if did == doc_id:
                                    file_path = fp; break
                            _aio.run(wiki_auto_update(
                                doc_id=doc_id, file_path=file_path,
                                collection_id=collection_id,
                            ))
                        except Exception:
                            logging.getLogger(__name__).debug('_poll failed', exc_info=True)
                    # v2.9: Auto-run ontology engine pipeline on changed docs
                    for doc_id in result.get("doc_ids", [])[:10]:
                        try:
                            import asyncio as _aio
                            from core.api.core_facade import auto_ontology_pipeline_for_doc
                            file_path = None
                            for fp, did in result.get("_path_map", {}).items():
                                if did == doc_id:
                                    file_path = fp; break
                            if file_path:
                                _aio.run(auto_ontology_pipeline_for_doc(
                                    doc_id=doc_id, file_path=file_path,
                                    collection_id=collection_id,
                                ))
                        except Exception:
                            logging.getLogger(__name__).debug('_poll failed', exc_info=True)
            except Exception as e:
                logging.debug(str(e), exc_info=True)
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
    except Exception as e:
        logging.debug(str(e), exc_info=True)
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
        except Exception as e:
            logging.debug(str(e), exc_info=True)

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
        except PermissionError as e:
            logging.debug(str(e), exc_info=True)
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
            except Exception as e:
                logging.debug(str(e), exc_info=True)
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
            except Exception as e:
                logging.debug(str(e), exc_info=True)

        # V1: Schema validation after conversion
        schema_ok = None
        try:
            from core.api.core_facade import read_page  # v2.5: CoreFacade
            from core.api.core_facade import validate_page_against_schema  # v2.5: CoreFacade
            saved = read_page(title, collection_id=collection_id, category=category)
            if saved:
                val = validate_page_against_schema(saved, collection_id=collection_id, mode="warning")
                schema_ok = val.is_valid
        except Exception as e:
            logging.debug(str(e), exc_info=True)

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
            except Exception as e:
                logging.debug(str(e), exc_info=True)
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
                        if fpath.name.startswith("."):
                            continue
                        file_path_str = str(fpath)
                        import concurrent.futures as _cf2
                        try:
                            with _cf2.ThreadPoolExecutor(max_workers=1) as _pool:
                                result = _pool.submit(asyncio.run,
                                    vault_to_wiki(file_path=file_path_str,
                                                  collection_id=collection_id,
                                                  vault_id=vault_id,
                                                  tenant_id=tenant_id)).result(timeout=120)
                                if result.get("status") in ("created", "skipped"):
                                    wikified += 1
                        except Exception as e:
                            logging.debug(str(e), exc_info=True)

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
                    except Exception as e:
                        logging.debug(str(e), exc_info=True)
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
