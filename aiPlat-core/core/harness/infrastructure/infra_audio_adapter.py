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

    async def synthesize(self, text: str, *, voice: str = "huayan", output_dir: str = "") -> str:
        """文本→语音 (Piper TTS 本地, 零网络零API Key).

        通过 ModelManager.select("tts") 从 llm_profile.yaml 读取配置,
        调用本地 piper 命令行生成 WAV 文件。

        Returns:
            生成的 WAV 文件路径
        """
        import uuid as _uuid, tempfile as _tempfile_

        out = output_dir or _tempfile_.gettempdir()
        output_path = f"{out}/tts_{_uuid.uuid4().hex[:8]}.wav"

        try:
            from core.harness.utils.model_injection import best_model_for_purpose
            model_name = best_model_for_purpose("tts")
        except Exception:
            model_name = "piper_zh_CN"

        model_path = os.path.expanduser("~/.aiplat/models/piper_zh_CN.onnx")
        if not os.path.isfile(model_path):
            # Try to resolve via ModelManager
            try:
                from core.harness.infrastructure.infra_bridge import get_infra_bridge
                bridge = get_infra_bridge()
                if bridge:
                    mgr = bridge.get_model_manager()
                    config = mgr.select("tts")
                    model_path = os.path.expanduser(
                        (config or {}).get("model_path", model_path)
                    )
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

        cmd = [
            "piper",
            "--model", model_path,
            "--output_file", output_path,
        ]

        proc = await __import__("asyncio").create_subprocess_exec(
            *cmd,
            stdin=__import__("asyncio").subprocess.PIPE,
            stdout=__import__("asyncio").subprocess.PIPE,
        )
        stdout, _ = await proc.communicate(input=text.encode("utf-8"))

        if proc.returncode == 0:
            logging.info("TTS synthesized: %s (%d bytes)", output_path, len(stdout) if stdout else 0)
            return output_path

        err = stdout.decode("utf-8", errors="ignore") if stdout else ""
        raise RuntimeError(f"Piper TTS failed (rc={proc.returncode}): {err[:200]}")


def create_infra_audio_adapter(**kwargs) -> InfraAudioAdapter:
    return InfraAudioAdapter(**kwargs)


__all__ = ["InfraAudioAdapter", "create_infra_audio_adapter"]
