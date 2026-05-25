"""
InfraAudioAdapter — bridges core audio (STT) to infra model management.

Wraps Whisper (faster-whisper / openai-whisper) through a managed adapter
consistent with other infra adapters.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

_whisper_model_cache: Any = None
_whisper_model_name: Optional[str] = None


def _resolve_whisper_model_name() -> str:
    return os.getenv("AIPLAT_VIDEO_WHISPER_MODEL", "base")


class InfraAudioAdapter:
    """Audio STT adapter through infra model management."""

    def __init__(self, *, model_name: str = ""):
        self._model_name = model_name or _resolve_whisper_model_name()
        self._device = os.getenv("AIPLAT_WHISPER_DEVICE", "cpu")
        self._compute_type = os.getenv("AIPLAT_WHISPER_COMPUTE_TYPE", "int8")

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> List[Dict[str, Any]]:
        # Try faster-whisper first
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel(self._model_name, device=self._device, compute_type=self._compute_type)
            lang = _normalize_language(language)
            segs, _info = model.transcribe(audio_path, language=lang, vad_filter=True)
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

        # Fallback to openai-whisper
        try:
            import whisper
            model = whisper.load_model(self._model_name)
            result = model.transcribe(audio_path, language=_normalize_language(language), verbose=False)
            out: List[Dict[str, Any]] = []
            for s in result.get("segments", []):
                txt = str(s.get("text", "")).strip()
                if not txt:
                    continue
                out.append({"start_ms": int(s.get("start", 0) * 1000), "end_ms": int(s.get("end", 0) * 1000), "text": txt})
            return out
        except Exception:
            pass

        raise RuntimeError("No Whisper backend available (faster-whisper or openai-whisper)")


def _normalize_language(language: Optional[str]) -> Optional[str]:
    lang = str(language or "").strip().lower()
    if not lang or lang in ("auto", "detect", "unknown", "none"):
        return None
    return lang


def create_infra_audio_adapter() -> InfraAudioAdapter:
    return InfraAudioAdapter()


__all__ = ["InfraAudioAdapter", "create_infra_audio_adapter"]
