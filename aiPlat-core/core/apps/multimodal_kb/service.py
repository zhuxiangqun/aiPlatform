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

from core.apps.multimodal_kb.db import KBSqlite
from core.apps.multimodal_kb.storage import get_tenant_storage

# Reuse PoC pipeline for now (A 阶段先收敛为技能/存储；后续可替换为 MinerU/Docling/自研结构化)
from core.apps.multimodal_kb_poc.ingest import ingest_scanned_pdf
from core.apps.multimodal_kb_poc.mineru_extract import (
    extract_tables_from_content_list,
    load_mineru_content_list,
    run_mineru_parse,
)
from core.apps.document_intelligence.embeddings import embed_text


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
        from core.apps.video_intelligence.service import ingest_video_document

        return ingest_video_document(
            tenant_id=tenant_id,
            collection_id=collection_id,
            file_path=file_path,
            kind="video",
            name=name,
            progress_cb=progress_cb,
            last_job_id=last_job_id,
        )

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


def query(
    *,
    tenant_id: str,
    collection_id: str,
    question: str,
    year: Optional[int] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    PoC → MVP Query：
    - 识别“投资/预算”类问题，默认 year=2026
    - 返回结构化预算条目 + citations（bbox+页图路径）
    """
    if not tenant_id:
        raise ValueError("tenant_id_required")
    if not collection_id:
        raise ValueError("collection_id_required")
    q = str(question or "").strip()
    if not q:
        raise ValueError("question_required")

    st = get_tenant_storage(tenant_id)
    db = KBSqlite(st.db_path)
    db.ensure_schema()

    wants_budget = ("预算" in q) or ("投资" in q)
    if not wants_budget:
        return {"answer": "当前 MVP 仅支持“投资预算”类问答。", "items": [], "citations": []}

    y = int(year or 2026)
    rows = db.list_budget_rows(tenant_id=st.tenant_id, collection_id=collection_id, year=y)

    items: List[Dict[str, Any]] = []
    citations: List[Dict[str, Any]] = []
    for r in rows:
        cells = r.get("cells") or {}
        if y == 2026:
            # Prefer y2026 column; fallback to total if table doesn't have per-year split.
            cell = (cells.get("y2026") or cells.get("total") or {}) if isinstance(cells, dict) else {}
            raw = cell.get("text")
            bbox = cell.get("bbox")
            amount = r.get("y2026") if r.get("y2026") is not None else r.get("total")
            if raw is None:
                # Fallback: show numeric value if structured amount exists
                if amount is None:
                    continue
                raw = str(amount)
            items.append(
                {
                    "item": r.get("item"),
                    "year": 2026,
                    "amount_raw": raw,
                    "amount": amount,
                    "unit": "万元",
                    "doc_id": r.get("doc_id"),
                    "page_idx": r.get("page_idx"),
                }
            )
            if bbox and r.get("page_image_path"):
                citations.append(
                    {
                        "doc_id": r.get("doc_id"),
                        "page_idx": r.get("page_idx"),
                        "asset_path": r.get("page_image_path"),
                        "bbox": bbox,
                        "extra": {"item": r.get("item"), "year": 2026, "raw": raw},
                    }
                )
        else:
            cell = (cells.get("y2027") or cells.get("total") or {}) if isinstance(cells, dict) else {}
            raw = cell.get("text")
            bbox = cell.get("bbox")
            amount = r.get("y2027") if r.get("y2027") is not None else r.get("total")
            if raw is None:
                if amount is None:
                    continue
                raw = str(amount)
            items.append(
                {
                    "item": r.get("item"),
                    "year": 2027,
                    "amount_raw": raw,
                    "amount": amount,
                    "unit": "万元",
                    "doc_id": r.get("doc_id"),
                    "page_idx": r.get("page_idx"),
                }
            )
            if bbox and r.get("page_image_path"):
                citations.append(
                    {
                        "doc_id": r.get("doc_id"),
                        "page_idx": r.get("page_idx"),
                        "asset_path": r.get("page_image_path"),
                        "bbox": bbox,
                        "extra": {"item": r.get("item"), "year": 2027, "raw": raw},
                    }
                )

        if len(items) >= int(limit):
            break

    answer = f"识别到 {y} 年投资预算条目 {len(items)} 条。"
    return {"answer": answer, "items": items, "citations": citations, "tenant_id": st.tenant_id, "collection_id": collection_id}


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
