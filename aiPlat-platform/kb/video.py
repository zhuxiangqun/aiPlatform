from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .intelligence.embeddings import embed_text
from .db import KBSqlite
from .storage import get_tenant_storage
from core.utils.ids import new_prefixed_id
from core.api.core_facade import (
    kb_transcribe_audio,
    kb_embed_text,
    kb_probe_video_duration,
    kb_extract_video_audio,
    kb_extract_video_keyframes,
    kb_ocr_keyframes,
)


def _safe_readable_path(p: str) -> bool:
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


def ingest_video_document(
    *,
    tenant_id: str,
    collection_id: str,
    file_path: str,
    kind: str = "video",
    name: str = "",
    progress_cb: Optional[Callable[[float, str, Dict[str, Any]], None]] = None,
    last_job_id: Optional[str] = None,
    source_url: Optional[str] = None,
) -> Dict[str, Any]:
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
    try:
        db.archive_doc_data(tenant_id=st.tenant_id, doc_id=doc_id)
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    db.upsert_document(
        tenant_id=st.tenant_id,
        doc_id=doc_id,
        collection_id=collection_id,
        source_uri=file_path,
        kind=kind,
        status="ingesting",
        meta={"last_job_id": last_job_id, "source_url": source_url},
    )

    out_dir = Path(st.assets_dir) / doc_id
    out_dir.mkdir(parents=True, exist_ok=True)
    audio_path = str(out_dir / "audio.wav")
    frames_dir = str(out_dir / "frames")

    # ── Try loading cached preview results (avoids re-running ffmpeg/Whisper/OCR) ──
    frame_interval_seconds = int(os.getenv("AIPLAT_VIDEO_KEYFRAME_INTERVAL_SECONDS", "15") or 15)
    cache_path = file_path + ".preview_cache.json"
    cached_segments = None
    try:
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.loads(f.read())
            if isinstance(cache, dict) and cache.get("kind") == "video":
                cached_segments = cache.get("segments") or []
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    if cached_segments and len(cached_segments) > 0:
        segments = cached_segments
        duration_ms = kb_probe_video_duration(file_path) if os.path.exists(file_path) else 0
        frames = []
        ocr_segments = []
    else:
        if progress_cb:
            progress_cb(0.05, "video_probe", {})
        duration_ms = kb_probe_video_duration(file_path)

        if progress_cb:
            progress_cb(0.15, "extract_audio", {})
        kb_extract_video_audio(file_path, audio_path)

        if progress_cb:
            progress_cb(0.35, "transcribe_audio", {})
        transcribe_diags: Dict[str, Any] = {}
        segments = kb_transcribe_audio(audio_path, language=os.getenv("AIPLAT_VIDEO_TRANSCRIBE_LANG", "auto"), diagnostics=transcribe_diags)
        if progress_cb:
            progress_cb(0.40, "transcribe_done", {
                "transcribe_model": transcribe_diags.get("model_name", ""),
                "transcribe_backend": transcribe_diags.get("backend", ""),
                "transcribe_segments": transcribe_diags.get("segment_count", 0),
                "transcribe_chars": transcribe_diags.get("total_chars", 0),
            })

        if progress_cb:
            progress_cb(0.75, "extract_keyframes", {})
        frames = kb_extract_video_keyframes(file_path, frames_dir, interval_seconds=frame_interval_seconds)
        ocr_segments = kb_ocr_keyframes(frames)

    if progress_cb:
        progress_cb(0.9, "persist_video_elements", {"segments": len(segments), "ocr_segments": len(ocr_segments), "frames": len(frames)})

    elements_batch: List[Dict[str, Any]] = []
    embeddings_batch: List[Dict[str, Any]] = []

    for idx, fr in enumerate(frames):
        db.insert_asset(
            tenant_id=st.tenant_id,
            asset_id=f"{doc_id}_frame_{idx:05d}",
            doc_id=doc_id,
            kind="frame_image",
            local_path=str(fr["local_path"]),
            page_idx=idx,
            time_ms=int(fr["time_ms"]),
            meta={"source": "video_keyframe"},
        )

    for idx, seg in enumerate(segments):
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        element_id = new_prefixed_id("el")
        elements_batch.append({
            "tenant_id": st.tenant_id, "element_id": element_id, "doc_id": doc_id,
            "type": "text", "page_idx": idx, "bbox": None, "text": text[:20000],
            "cells": None, "asset_id": None,
            "meta": {
                "source": "video_transcript",
                "start_ms": int(seg.get("start_ms") or 0),
                "end_ms": int(seg.get("end_ms") or 0),
            },
        })
        embeddings_batch.append({
            "tenant_id": st.tenant_id,
            "embedding_id": new_prefixed_id("emb"),
            "doc_id": doc_id, "element_id": element_id,
            "embedding_type": "text",
            "vector": embed_text(text[:4000]),
            "model": "hash-128",
        })

    for idx, seg in enumerate(ocr_segments):
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        element_id = new_prefixed_id("el")
        page_idx = idx + len(segments)
        elements_batch.append({
            "tenant_id": st.tenant_id, "element_id": element_id, "doc_id": doc_id,
            "type": "text", "page_idx": page_idx, "bbox": None, "text": text[:20000],
            "cells": None, "asset_id": None,
            "meta": {
                "source": "video_ocr",
                "time_ms": int(seg.get("time_ms") or 0),
                "start_ms": int(seg.get("time_ms") or 0),
                "end_ms": int(seg.get("time_ms") or 0),
            },
        })
        embeddings_batch.append({
            "tenant_id": st.tenant_id,
            "embedding_id": new_prefixed_id("emb"),
            "doc_id": doc_id, "element_id": element_id,
            "embedding_type": "text",
            "vector": embed_text(text[:4000]),
            "model": "hash-128",
        })

    # ── Full punctuated transcript as single element (for whole-doc retrieval) ──
    try:
        from kb.service import _format_transcript_with_punctuation
        full_text = _format_transcript_with_punctuation(segments)
        if full_text and len(full_text) > 50:
            full_eid = new_prefixed_id("el")
            elements_batch.append({
                "tenant_id": st.tenant_id, "element_id": full_eid, "doc_id": doc_id,
                "type": "paragraph", "page_idx": 0, "bbox": None, "text": full_text[:80000],
                "cells": None, "asset_id": None,
                "meta": {"source": "video_transcript_full"},
            })
            embeddings_batch.append({
                "tenant_id": st.tenant_id,
                "embedding_id": new_prefixed_id("emb"),
                "doc_id": doc_id, "element_id": full_eid,
                "embedding_type": "paragraph",
                "vector": embed_text(full_text[:4000]),
                "model": "hash-128",
            })

            # ── Also insert chunked version for finer retrieval ──
            try:
                from core.api.facades.kb_facade import kb_chunk_elements
                para_element = [{"type": "paragraph", "text": full_text, "page_idx": 0}]
                para_chunks = kb_chunk_elements(para_element, kind="markdown", target_size=1000, overlap=150)
                for ci, ch in enumerate(para_chunks):
                    ceid = new_prefixed_id("el")
                    elements_batch.append({
                        "tenant_id": st.tenant_id, "element_id": ceid, "doc_id": doc_id,
                        "type": "text", "page_idx": 0, "bbox": None, "text": ch["text"][:20000],
                        "cells": None, "asset_id": None,
                        "meta": {"source": "video_transcript_full",
                                 "chunk_index": ci, "chunk_total": len(para_chunks),
                                 "chunk_strategy": "structured"},
                    })
                    embeddings_batch.append({
                        "tenant_id": st.tenant_id,
                        "embedding_id": new_prefixed_id("emb"),
                        "doc_id": doc_id, "element_id": ceid,
                        "embedding_type": "text",
                        "vector": embed_text(ch["text"][:4000]),
                        "model": "hash-128",
                    })
            except Exception as e:
                logging.debug(str(e), exc_info=True)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    if elements_batch:
        # Delete old elements before re-inserting (reingest safety)
        with db.connect() as conn:
            conn.execute("DELETE FROM kb_elements WHERE doc_id=?", (doc_id,))
            conn.execute("DELETE FROM kb_embeddings WHERE doc_id=?", (doc_id,))
        db.insert_elements_batch(elements=elements_batch)
    if embeddings_batch:
        db.insert_embeddings_batch(embeddings=embeddings_batch)

    total_content_segments = len([s for s in segments if str(s.get("text") or "").strip()]) + len([s for s in ocr_segments if str(s.get("text") or "").strip()])
    if total_content_segments <= 0:
        db.upsert_document(
            tenant_id=st.tenant_id,
            doc_id=doc_id,
            collection_id=collection_id,
            source_uri=file_path,
            kind=kind,
            status="failed",
            meta={
                "duration_ms": duration_ms,
                "segments": len(segments),
                "ocr_segments": len(ocr_segments),
                "frames": len(frames),
                "frame_interval_seconds": frame_interval_seconds,
                "last_job_id": last_job_id,
                "source_url": source_url,
                "error": "no_video_content_extracted",
            },
        )
        raise RuntimeError("no_video_content_extracted")

    db.upsert_document(
        tenant_id=st.tenant_id,
        doc_id=doc_id,
        collection_id=collection_id,
        source_uri=file_path,
        kind=kind,
        status="ready",
        meta={
            "duration_ms": duration_ms,
            "segments": len(segments),
            "ocr_segments": len(ocr_segments),
            "frames": len(frames),
            "frame_interval_seconds": frame_interval_seconds,
            "last_job_id": last_job_id,
            "source_url": source_url,
        },
    )

    return {
        "tenant_id": st.tenant_id,
        "collection_id": collection_id,
        "doc_id": doc_id,
        "duration_ms": duration_ms,
        "segments": len(segments),
        "ocr_segments": len(ocr_segments),
        "frames": len(frames),
        "assets_dir": str(out_dir),
    }
