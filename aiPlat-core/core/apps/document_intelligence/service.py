from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import threading
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core.apps.multimodal_kb.db import KBSqlite
from core.apps.multimodal_kb.service import ingest_document
from core.apps.multimodal_kb.storage import get_tenant_storage
from core.apps.document_intelligence.embeddings import embed_text
from core.utils.ids import new_prefixed_id


class _TextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._texts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip_depth += 1

    def handle_endtag(self, tag: str):
        if tag in ("script", "style", "noscript") and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str):
        if self._skip_depth > 0:
            return
        s = (data or "").strip()
        if s:
            self._texts.append(s)

    def text(self) -> str:
        # Keep it bounded; later can chunk.
        return "\n".join(self._texts)[:200000]


def _guess_kind_from_url_and_ct(url: str, content_type: str) -> str:
    u = (url or "").lower()
    ct = (content_type or "").lower()
    if ct.startswith("video/") or any(u.endswith(ext) for ext in (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v")):
        return "video"
    if "text/html" in ct or u.endswith(".html") or u.endswith(".htm"):
        return "html"
    if "application/pdf" in ct or u.endswith(".pdf"):
        return "pdf"
    return "pdf"


def _detect_charset_from_content_type(content_type: str) -> Optional[str]:
    ct = (content_type or "")
    m = None
    try:
        import re

        m = re.search(r"charset=([A-Za-z0-9_\-]+)", ct, re.I)
    except Exception:
        m = None
    return m.group(1) if m else None


def _download_url_to_tenant(tenant_id: str, url: str, prefer_kind: Optional[str] = None) -> Tuple[str, str, str, str, str]:
    """
    Download a URL into tenant uploads directory and return local file path.
    MVP: supports direct file URLs (PDF) and HTML pages.
    Returns: (local_path, detected_kind, content_type, etag, last_modified)
    """
    st = get_tenant_storage(tenant_id)
    up_dir = Path(st.uploads_dir)
    up_dir.mkdir(parents=True, exist_ok=True)

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "file":
        # file://... local path
        src = Path(urllib.request.url2pathname(parsed.path))
        if not src.exists():
            raise RuntimeError("url_file_not_found")
        # copy to uploads for provenance
        h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
        safe = "".join([c if c.isalnum() or c in "._-" else "_" for c in (src.name or "file.bin")])[:120]
        dst = up_dir / f"url_{h}_{safe}"
        dst.write_bytes(src.read_bytes())
        kind = _guess_kind_from_url_and_ct(url, "")
        return str(dst), kind, "", "", ""

    name = os.path.basename(parsed.path) or "download.bin"
    safe = "".join([c if c.isalnum() or c in "._-" else "_" for c in name])[:120]
    # unique name by url hash
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    dst = up_dir / f"url_{h}_{safe}"

    # Simple download (no auth/cookies). For enterprise use, extend with headers/cookies.
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "aiPlat/0.1 (+doc_ingest)",
            "Accept": "*/*",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=int(os.getenv("AIPLAT_URL_TIMEOUT_SECONDS", "30"))) as resp:
        data = resp.read()
        content_type = str(resp.headers.get("Content-Type") or "")
        etag = str(resp.headers.get("ETag") or "")
        last_modified = str(resp.headers.get("Last-Modified") or "")
    kind = _guess_kind_from_url_and_ct(url, content_type)
    if prefer_kind == "video" and kind == "html":
        ytdlp = shutil.which("yt-dlp")
        if not ytdlp:
            raise RuntimeError("video_page_requires_ytdlp")
        out_tpl = str(up_dir / f"video_{h}.%(ext)s")
        subprocess.run(
            [ytdlp, "--no-playlist", "-o", out_tpl, url],
            check=True,
            capture_output=True,
            text=True,
        )
        matches = sorted(up_dir.glob(f"video_{h}.*"))
        if not matches:
            raise RuntimeError("video_download_failed")
        return str(matches[0]), "video", "video/*", "", ""
    if len(data) > 500 * 1024 * 1024:
        raise RuntimeError("file_too_large")
    dst.write_bytes(data)
    return str(dst), kind, content_type, etag, last_modified


def enqueue_doc_ingest(
    *,
    tenant_id: str,
    collection_id: str,
    file_path: Optional[str] = None,
    url: Optional[str] = None,
    kind: str = "pdf",
    ocr_lang: str = "zh",
    ocr_engine: Optional[str] = None,
    dpi: int = 240,
    max_pages: Optional[int] = 60,
    force_reingest: bool = False,
) -> Dict[str, Any]:
    """
    Platform-facing doc ingest entry.
    - Supports local file_path OR url (download first).
    - Delegates to existing ingest_document pipeline (which now also writes kb_elements).
    - Uses kb_jobs/kb_job_events for observability.
    """
    if not tenant_id:
        tenant_id = "default"
    if not collection_id:
        collection_id = "default"
    if not file_path and not url:
        raise ValueError("file_path_or_url_required")

    st = get_tenant_storage(tenant_id)
    db = KBSqlite(st.db_path)
    db.ensure_schema()
    db.upsert_collection(tenant_id=st.tenant_id, collection_id=collection_id, name="")

    cache_hit = False
    cache_row = None
    cache_known = False
    content_type = ""
    etag = ""
    last_modified = ""
    content_hash = None

    # Resolve url → local file (with url_cache reuse)
    if url and not file_path:
        cache_row = db.get_url_cache(tenant_id=st.tenant_id, url=url)
        cache_known = cache_row is not None
        if cache_row and os.path.exists(str(cache_row.get("local_path") or "")):
            file_path = str(cache_row["local_path"])
            kind = kind or str(cache_row.get("kind") or "") or "pdf"
            content_type = str(cache_row.get("content_type") or "")
            content_hash = str(cache_row.get("content_hash") or "") or None
            cache_hit = True
        else:
            file_path, detected_kind, content_type, etag, last_modified = _download_url_to_tenant(tenant_id, url, prefer_kind=kind)
            kind = kind or detected_kind or "pdf"

    assert file_path

    # Deterministic-ish doc_id by file hash (same as multimodal_kb.service)
    try:
        if content_hash:
            sha = content_hash[:12]
        else:
            content_hash = hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
            sha = content_hash[:12]
        doc_id = f"doc_{sha}"
    except Exception:
        doc_id = new_prefixed_id("doc")

    job_id = new_prefixed_id("job")

    # Idempotency (best-effort):
    # - We compute doc_id from file bytes when possible (below).
    # - If doc exists and ready, skip re-ingest unless forced.
    force = force_reingest or (str(os.getenv("AIPLAT_FORCE_REINGEST", "0")).strip() in ("1", "true", "yes"))
    # Record source (always) for provenance.
    source_id = new_prefixed_id("src")
    source_type = "url" if url else "upload"
    db.insert_doc_source(
        tenant_id=st.tenant_id,
        source_id=source_id,
        doc_id=doc_id,
        source_type=source_type,
        source_uri=url or file_path,
        url=url,
        local_path=file_path,
        kind=kind,
        content_type=content_type or None,
        content_hash=content_hash,
        meta={"cache_hit": cache_hit},
    )

    # URL cache upsert (only for url sources)
    if url and file_path:
        db.upsert_url_cache(
            tenant_id=st.tenant_id,
            url=url,
            doc_id=doc_id,
            local_path=file_path,
            kind=kind,
            content_type=content_type or None,
            content_hash=content_hash,
            etag=etag or None,
            last_modified=last_modified or None,
            meta={"last_source_id": source_id},
        )

    # URL dedupe (strong): if this doc_id already has parsed elements, short-circuit.
    # Do not rely on documents.status because it can race with async ingestion.
    if url and (not force):
        existing_elements = db.count_elements(tenant_id=st.tenant_id, doc_id=doc_id)
        if existing_elements > 0:
            db.create_job(
                tenant_id=st.tenant_id,
                job_id=job_id,
                type="ingest",
                collection_id=collection_id,
                doc_id=doc_id,
                status="completed",
                progress=1.0,
                message="dedupe_hit",
                input={
                    "tenant_id": tenant_id,
                    "collection_id": collection_id,
                    "file_path": file_path,
                    "url": url,
                    "kind": kind,
                    "ocr_lang": ocr_lang,
                    "ocr_engine": ocr_engine,
                    "dpi": dpi,
                    "max_pages": max_pages,
                },
            )
            db.update_job(
                tenant_id=st.tenant_id,
                job_id=job_id,
                output={
                    "tenant_id": st.tenant_id,
                    "collection_id": collection_id,
                    "doc_id": doc_id,
                    "job_id": job_id,
                    "dedupe": True,
                    "cache_hit": cache_hit,
                    "cache_known": cache_known,
                    "elements": existing_elements,
                },
            )
            db.append_job_event(
                tenant_id=st.tenant_id,
                job_id=job_id,
                level="info",
                message="dedupe_hit",
                extra={"doc_id": doc_id, "cache_hit": cache_hit, "cache_known": cache_known, "elements": existing_elements},
            )
            return {
                "tenant_id": st.tenant_id,
                "collection_id": collection_id,
                "doc_id": doc_id,
                "job_id": job_id,
                "dedupe": True,
                "cache_hit": cache_hit,
                "cache_known": cache_known,
            }

    # Dedupe before changing document status.
    if not force:
        try:
            with db.connect() as conn:
                row = conn.execute(
                    "SELECT status FROM documents WHERE tenant_id=? AND doc_id=?",
                    (st.tenant_id, doc_id),
                ).fetchone()
            if row and str(row["status"]) == "ready":
                db.create_job(
                    tenant_id=st.tenant_id,
                    job_id=job_id,
                    type="ingest",
                    collection_id=collection_id,
                    doc_id=doc_id,
                    status="completed",
                    progress=1.0,
                    message="dedupe_hit",
                    input={"tenant_id": tenant_id, "collection_id": collection_id, "file_path": file_path, "url": url, "kind": kind, "ocr_lang": ocr_lang, "ocr_engine": ocr_engine, "dpi": dpi, "max_pages": max_pages},
                    output={"tenant_id": st.tenant_id, "collection_id": collection_id, "doc_id": doc_id, "job_id": job_id, "dedupe": True, "cache_hit": cache_hit, "cache_known": cache_known, "elements": db.count_elements(tenant_id=st.tenant_id, doc_id=doc_id)},
                )
                db.append_job_event(tenant_id=st.tenant_id, job_id=job_id, level="info", message="dedupe_hit", extra={"doc_id": doc_id, "cache_hit": cache_hit})
                return {"tenant_id": st.tenant_id, "collection_id": collection_id, "doc_id": doc_id, "job_id": job_id, "dedupe": True, "cache_hit": cache_hit, "cache_known": cache_known}
        except Exception:
            pass

    db.upsert_document(
        tenant_id=st.tenant_id,
        doc_id=doc_id,
        collection_id=collection_id,
        source_uri=file_path,
        kind=kind or "pdf",
        status="queued",
        meta={"ocr_lang": ocr_lang, "ocr_engine": ocr_engine, "dpi": dpi, "max_pages": max_pages, "last_job_id": job_id, "url": url},
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
        input={"tenant_id": tenant_id, "collection_id": collection_id, "file_path": file_path, "url": url, "kind": kind, "ocr_lang": ocr_lang, "ocr_engine": ocr_engine, "dpi": dpi, "max_pages": max_pages},
    )
    db.append_job_event(tenant_id=st.tenant_id, job_id=job_id, level="info", message="queued", extra={})

    def _runner() -> None:
        db2 = KBSqlite(st.db_path)
        try:
            db2.update_job(tenant_id=st.tenant_id, job_id=job_id, status="running", progress=0.01, message="start")
            db2.append_job_event(tenant_id=st.tenant_id, job_id=job_id, level="info", message="start", extra={})
            if (kind or "").lower() == "html":
                # Parse HTML and store as a single text element (MVP).
                raw_bytes = Path(file_path).read_bytes()
                # Best-effort charset detection: meta/http header isn't available at this point, so
                # try utf-8 then fall back to latin-1.
                try:
                    raw = raw_bytes.decode("utf-8")
                except Exception:
                    raw = raw_bytes.decode("latin-1", errors="ignore")
                p = _TextHTMLParser()
                p.feed(raw)
                text = p.text().strip()
                if not text:
                    text = raw.strip()[:200000]
                # overwrite document status to ready + insert element
                element_id = new_prefixed_id("el")
                db2.insert_element(
                    tenant_id=st.tenant_id,
                    element_id=element_id,
                    doc_id=doc_id,
                    type="text",
                    page_idx=None,
                    bbox=None,
                    text=text,
                    cells=None,
                    asset_id=None,
                    meta={"source": "html", "url": url, "cache_hit": cache_hit},
                )
                db2.insert_embedding(
                    tenant_id=st.tenant_id,
                    embedding_id=new_prefixed_id("emb"),
                    doc_id=doc_id,
                    element_id=element_id,
                    embedding_type="text",
                    vector=embed_text(text[:4000]),
                    model="hash-128",
                )
                out = {"tenant_id": st.tenant_id, "collection_id": collection_id, "doc_id": doc_id, "pages": 0, "budget_rows": 0, "budget_pages": [], "assets_dir": str(Path(st.assets_dir) / doc_id)}
                db2.upsert_document(
                    tenant_id=st.tenant_id,
                    doc_id=doc_id,
                    collection_id=collection_id,
                    source_uri=file_path,
                    kind=kind,
                    status="ready",
                    meta={"pages": 0, "ocr_lang": ocr_lang, "ocr_engine": ocr_engine, "dpi": dpi, "max_pages": max_pages, "last_job_id": job_id, "url": url},
                )
            else:
                out = ingest_document(
                    tenant_id=tenant_id,
                    collection_id=collection_id,
                    file_path=file_path,
                    kind=kind or "pdf",
                    ocr_lang=ocr_lang,
                    ocr_engine=ocr_engine,
                    dpi=dpi,
                    max_pages=max_pages,
                    name="",
                    last_job_id=job_id,
                )
            db2.update_job(tenant_id=st.tenant_id, job_id=job_id, status="completed", progress=1.0, message="completed", output=out)
            db2.append_job_event(tenant_id=st.tenant_id, job_id=job_id, level="info", message="completed", extra={})
        except Exception as e:
            db2.update_job(tenant_id=st.tenant_id, job_id=job_id, status="failed", progress=1.0, message=str(e), error={"code": "EXCEPTION", "message": str(e)})
            db2.append_job_event(tenant_id=st.tenant_id, job_id=job_id, level="error", message="failed", extra={"error": str(e)})


    threading.Thread(target=_runner, name=f"doc_ingest_{job_id}", daemon=True).start()

    return {"tenant_id": st.tenant_id, "collection_id": collection_id, "doc_id": doc_id, "job_id": job_id, "cache_hit": cache_hit, "cache_known": cache_known}
