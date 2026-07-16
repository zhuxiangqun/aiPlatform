"""
InfraAudioAdapter — audio STT through infra model management.
Inherits BaseModelAdapter for shared model resolution + caching.
"""

from __future__ import annotations
import logging

import os
from typing import Any, Dict, List, Optional

from .base_model_adapter import BaseModelAdapter


def _normalize_language(language: Optional[str]) -> Optional[str]:
    lang = str(language or "").strip().lower()
    if not lang or lang in ("auto", "detect", "unknown", "none"):
        return None
    return lang


class InfraAudioAdapter(BaseModelAdapter):
    capability = "audio"

    def __init__(self, *, model_name: str = ""):
        super().__init__(model_name=model_name)
        self._device = os.getenv("AIPLAT_WHISPER_DEVICE", "cpu")
        self._compute_type = os.getenv("AIPLAT_WHISPER_COMPUTE_TYPE", "int8")

    def _load_model(self, name: str) -> Any:  # noqa: boundary — adapter override, loaded per-call
        pass  # Whisper model loaded per-call, not cached globally

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> List[Dict[str, Any]]:
        lang = _normalize_language(language)
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel(self._model_name, device=self._device, compute_type=self._compute_type)
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
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        try:
            import whisper
            model = whisper.load_model(self._model_name)  # noqa: boundary — adapter's own whisper fallback
            result = model.transcribe(audio_path, language=lang, verbose=False)
            return [{"start_ms": int(s.get("start", 0) * 1000),
                     "end_ms": int(s.get("end", 0) * 1000),
                     "text": str(s.get("text", "")).strip()}
                    for s in result.get("segments", [])]
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        raise RuntimeError("No Whisper backend available (faster-whisper or openai-whisper)")


def create_infra_audio_adapter(**kwargs) -> InfraAudioAdapter:
    return InfraAudioAdapter(**kwargs)


__all__ = ["InfraAudioAdapter", "create_infra_audio_adapter"]
