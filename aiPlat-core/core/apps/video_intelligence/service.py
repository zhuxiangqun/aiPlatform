from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.apps.document_intelligence.embeddings import embed_text
from core.apps.multimodal_kb.db import KBSqlite
from core.apps.multimodal_kb.storage import get_tenant_storage
from core.utils.ids import new_prefixed_id


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


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def _require_bin(name: str) -> str:
    p = shutil.which(name)
    if not p:
        raise RuntimeError(f"{name}_not_found")
    return p


def _probe_duration_ms(video_path: str) -> int:
    ffprobe = _require_bin("ffprobe")
    cp = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
    )
    try:
        return int(float((cp.stdout or "0").strip()) * 1000)
    except Exception:
        return 0


def _extract_audio(video_path: str, audio_path: str) -> None:
    ffmpeg = _require_bin("ffmpeg")
    _run([ffmpeg, "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", audio_path])


def _normalize_transcribe_language(language: Optional[str]) -> Optional[str]:
    lang = str(language or "").strip().lower()
    if not lang or lang in ("auto", "detect", "unknown", "none"):
        return None
    return lang


def _transcribe_audio(audio_path: str, language: Optional[str] = None) -> List[Dict[str, Any]]:
    model_name = os.getenv("AIPLAT_VIDEO_WHISPER_MODEL", "base")
    whisper_language = _normalize_transcribe_language(language)
    # 1) faster-whisper
    try:
        from faster_whisper import WhisperModel  # type: ignore

        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        segs, _info = model.transcribe(audio_path, language=whisper_language, vad_filter=True)
        out: List[Dict[str, Any]] = []
        for s in segs:
            txt = str(getattr(s, "text", "") or "").strip()
            if not txt:
                continue
            out.append(
                {
                    "start_ms": int(float(getattr(s, "start", 0.0)) * 1000),
                    "end_ms": int(float(getattr(s, "end", 0.0)) * 1000),
                    "text": txt,
                }
            )
        return out
    except Exception:
        pass

    # 2) openai-whisper
    try:
        import whisper  # type: ignore

        model = whisper.load_model(model_name)
        result = model.transcribe(audio_path, language=whisper_language, verbose=False)
        out: List[Dict[str, Any]] = []
        for s in list((result or {}).get("segments") or []):
            txt = str(s.get("text") or "").strip()
            if not txt:
                continue
            out.append(
                {
                    "start_ms": int(float(s.get("start") or 0.0) * 1000),
                    "end_ms": int(float(s.get("end") or 0.0) * 1000),
                    "text": txt,
                }
            )
        return out
    except Exception:
        pass

    raise RuntimeError("whisper_not_installed")


def _extract_keyframes(video_path: str, frames_dir: str, interval_seconds: int = 15) -> List[Dict[str, Any]]:
    ffmpeg = _require_bin("ffmpeg")
    Path(frames_dir).mkdir(parents=True, exist_ok=True)
    out_tpl = str(Path(frames_dir) / "frame_%05d.jpg")
    fps_expr = f"fps=1/{max(1, int(interval_seconds))}"
    _run([ffmpeg, "-y", "-i", video_path, "-vf", fps_expr, out_tpl])
    files = sorted(Path(frames_dir).glob("frame_*.jpg"))
    out: List[Dict[str, Any]] = []
    for idx, p in enumerate(files):
        out.append({"local_path": str(p), "time_ms": idx * max(1, int(interval_seconds)) * 1000})
    return out


def _ocr_keyframes(frames: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    try:
        from PIL import Image  # type: ignore
        import pytesseract  # type: ignore
    except Exception:
        return []

    lang = str(os.getenv("AIPLAT_VIDEO_OCR_LANG", "eng+chi_sim") or "eng+chi_sim")
    out: List[Dict[str, Any]] = []
    for fr in frames:
        p = str(fr.get("local_path") or "")
        if not p:
            continue
        try:
            with Image.open(p) as img:
                text = pytesseract.image_to_string(img, lang=lang)
        except Exception:
            continue
        text = " ".join(str(text or "").split()).strip()
        if len(text) < 6:
            continue
        useful = len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", text))
        symbol = len(re.findall(r"[^A-Za-z0-9\u4e00-\u9fff\s]", text))
        quality = (useful / max(1, len(text))) - (symbol / max(1, len(text))) * 0.7
        if useful < max(6, len(text) // 4) or quality < 0.28:
            continue
        out.append(
            {
                "time_ms": int(fr.get("time_ms") or 0),
                "text": text[:4000],
            }
        )
    return out


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
        meta={"last_job_id": last_job_id, "source_url": source_url},
    )

    out_dir = Path(st.assets_dir) / doc_id
    out_dir.mkdir(parents=True, exist_ok=True)
    audio_path = str(out_dir / "audio.wav")
    frames_dir = str(out_dir / "frames")

    if progress_cb:
        progress_cb(0.05, "video_probe", {})
    duration_ms = _probe_duration_ms(file_path)

    if progress_cb:
        progress_cb(0.15, "extract_audio", {})
    _extract_audio(file_path, audio_path)

    if progress_cb:
        progress_cb(0.35, "transcribe_audio", {})
    segments = _transcribe_audio(audio_path, language=os.getenv("AIPLAT_VIDEO_TRANSCRIBE_LANG", "auto"))

    if progress_cb:
        progress_cb(0.75, "extract_keyframes", {})
    frame_interval_seconds = int(os.getenv("AIPLAT_VIDEO_KEYFRAME_INTERVAL_SECONDS", "15") or 15)
    frames = _extract_keyframes(file_path, frames_dir, interval_seconds=frame_interval_seconds)
    ocr_segments = _ocr_keyframes(frames)

    if progress_cb:
        progress_cb(0.9, "persist_video_elements", {"segments": len(segments), "ocr_segments": len(ocr_segments), "frames": len(frames)})

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
        db.insert_element(
            tenant_id=st.tenant_id,
            element_id=element_id,
            doc_id=doc_id,
            type="text",
            page_idx=idx,
            bbox=None,
            text=text[:20000],
            cells=None,
            asset_id=None,
            meta={
                "source": "video_transcript",
                "start_ms": int(seg.get("start_ms") or 0),
                "end_ms": int(seg.get("end_ms") or 0),
            },
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

    for idx, seg in enumerate(ocr_segments):
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        element_id = new_prefixed_id("el")
        page_idx = idx + len(segments)
        db.insert_element(
            tenant_id=st.tenant_id,
            element_id=element_id,
            doc_id=doc_id,
            type="text",
            page_idx=page_idx,
            bbox=None,
            text=text[:20000],
            cells=None,
            asset_id=None,
            meta={
                "source": "video_ocr",
                "time_ms": int(seg.get("time_ms") or 0),
                "start_ms": int(seg.get("time_ms") or 0),
                "end_ms": int(seg.get("time_ms") or 0),
            },
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
