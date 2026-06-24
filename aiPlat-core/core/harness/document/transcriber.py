"""
Audio transcriber — Whisper model inference for speech-to-text.

Backends (tried in order):
  1. faster-whisper (local CTranslate2)
  2. openai-whisper (local PyTorch)
  3. Raise RuntimeError if neither available

Configuration:
  model env var  — model size (base/small/medium/large, default: base), resolved via resolve_model_name("audio")
  AIPLAT_VIDEO_TRANSCRIBE_LANG — language hint (zh/en/auto, default: auto)

Callers:
  - core/harness/document/video.py (VideoIngestPipeline)
  - platform/kb/video.py (ingest_video_document) via video.py
  - Any agent that needs speech-to-text capability
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional


def _normalize_language(language: Optional[str]) -> Optional[str]:
    lang = str(language or "").strip().lower()
    if not lang or lang in ("auto", "detect", "unknown", "none"):
        return None
    return lang


def _fill_diagnostics(diagnostics: Dict[str, Any], segments: List[Dict[str, Any]]) -> None:
    diagnostics["segment_count"] = len(segments)
    diagnostics["total_chars"] = sum(len(str(s.get("text", ""))) for s in segments)
    diagnostics["last_end_ms"] = segments[-1]["end_ms"] if segments else 0


def transcribe_audio(
    audio_path: str,
    language: Optional[str] = None,
    diagnostics: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Transcribe audio to text segments.

    Args:
        diagnostics: If provided, populated in-place with:
            model_name, backend, segment_count, total_chars, last_end_ms
    """
    if diagnostics is None:
        diagnostics = {}
    whisper_language = _normalize_language(language)
    device = os.getenv("AIPLAT_WHISPER_DEVICE", "cpu")
    compute_type = os.getenv("AIPLAT_WHISPER_COMPUTE_TYPE", "int8")

    # Prefer InfraAudioAdapter (unified model loading)
    try:
        from core.harness.infrastructure.base_model_adapter import create_adapter, resolve_model_name
        adapter = create_adapter("audio")
        diagnostics["model_name"] = resolve_model_name("audio")
        diagnostics["backend"] = "infra_audio_adapter"
        result = adapter.transcribe(audio_path, language)
        _fill_diagnostics(diagnostics, result)
        return result
    except Exception:
        pass

    model_name = resolve_model_name("audio")

    try:
        from faster_whisper import WhisperModel

        diagnostics["model_name"] = model_name
        diagnostics["backend"] = "faster-whisper"
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
        segs, _info = model.transcribe(audio_path, language=whisper_language, vad_filter=True)
        out: List[Dict[str, Any]] = []
        for s in segs:
            txt = str(getattr(s, "text", "") or "").strip()
            if not txt:
                continue
            out.append({
                "start_ms": int(float(getattr(s, "start", 0.0)) * 1000),
                "end_ms": int(float(getattr(s, "end", 0.0)) * 1000),
                "text": txt,
            })
        _fill_diagnostics(diagnostics, out)
        return out
    except Exception:
        pass

    try:
        import whisper

        diagnostics["model_name"] = model_name
        diagnostics["backend"] = "openai-whisper"
        model = whisper.load_model(model_name)
        result = model.transcribe(audio_path, language=whisper_language, verbose=False)
        out: List[Dict[str, Any]] = []
        for s in list((result or {}).get("segments") or []):
            txt = str(s.get("text") or "").strip()
            if not txt:
                continue
            out.append({
                "start_ms": int(float(s.get("start") or 0.0) * 1000),
                "end_ms": int(float(s.get("end") or 0.0) * 1000),
                "text": txt,
            })
        _fill_diagnostics(diagnostics, out)
        return out
    except Exception:
        pass

    raise RuntimeError("whisper_not_installed")


def transcribe_audio_chunked(
    audio_path: str,
    language: Optional[str] = None,
    chunk_seconds: int = 60,
) -> List[Dict[str, Any]]:
    """Split audio into chunks, transcribe each, merge with corrected timestamps.

    Used as a fallback when full-audio transcription has low coverage
    (indicating ffmpeg timeout or Whisper failure on long audio).
    """
    tmpdir = tempfile.mkdtemp(prefix="whisper_chunks_")
    try:
        chunks_dir = os.path.join(tmpdir, "chunks")
        os.makedirs(chunks_dir, exist_ok=True)
        chunk_pattern = os.path.join(chunks_dir, "chunk_%04d.wav")
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path, "-f", "segment",
             "-segment_time", str(chunk_seconds), "-ar", "16000", "-ac", "1",
             chunk_pattern],
            check=True, capture_output=True, text=True, timeout=300,
        )

        chunk_files = sorted([
            f for f in os.listdir(chunks_dir) if f.endswith(".wav")
        ])

        all_segments: List[Dict[str, Any]] = []
        for idx, chunk_file in enumerate(chunk_files):
            chunk_path = os.path.join(chunks_dir, chunk_file)
            chunk_segs = transcribe_audio(chunk_path, language=language)
            offset_ms = idx * chunk_seconds * 1000
            for seg in chunk_segs:
                seg["start_ms"] = seg.get("start_ms", 0) + offset_ms
                seg["end_ms"] = seg.get("end_ms", 0) + offset_ms
            all_segments.extend(chunk_segs)

        return all_segments
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


__all__ = ["transcribe_audio", "transcribe_audio_chunked"]
