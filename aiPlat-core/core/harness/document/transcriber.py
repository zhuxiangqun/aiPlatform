"""
Audio transcriber — Whisper model inference for speech-to-text.

Backends (tried in order):
  1. faster-whisper (local CTranslate2)
  2. openai-whisper (local PyTorch)
  3. Raise RuntimeError if neither available

Configuration:
  AIPLAT_VIDEO_WHISPER_MODEL  — model size (base/small/medium/large, default: base)
  AIPLAT_VIDEO_TRANSCRIBE_LANG — language hint (zh/en/auto, default: auto)

Callers:
  - core/harness/document/video.py (VideoIngestPipeline)
  - platform/kb/video.py (ingest_video_document) via video.py
  - Any agent that needs speech-to-text capability
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


def _normalize_language(language: Optional[str]) -> Optional[str]:
    lang = str(language or "").strip().lower()
    if not lang or lang in ("auto", "detect", "unknown", "none"):
        return None
    return lang


def transcribe_audio(audio_path: str, language: Optional[str] = None) -> List[Dict[str, Any]]:
    model_name = os.getenv("AIPLAT_VIDEO_WHISPER_MODEL", "base")  # noqa: env-legacy
    whisper_language = _normalize_language(language)
    device = os.getenv("AIPLAT_WHISPER_DEVICE", "cpu")
    compute_type = os.getenv("AIPLAT_WHISPER_COMPUTE_TYPE", "int8")

    # Prefer InfraAudioAdapter (unified model loading)
    try:
        from core.harness.infrastructure.base_model_adapter import create_adapter
        adapter = create_adapter("audio")
        return adapter.transcribe(audio_path, language)
    except Exception:
        pass

    try:
        from faster_whisper import WhisperModel

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
        return out
    except Exception:
        pass

    try:
        import whisper

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
        return out
    except Exception:
        pass

    raise RuntimeError("whisper_not_installed")


__all__ = ["transcribe_audio"]
