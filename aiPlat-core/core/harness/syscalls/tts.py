"""
sys_tts — Text-to-Speech syscall (Piper TTS backend, local-only).

Uses local Piper TTS via InfraAudioAdapter.synthesize().
Zero network, zero API key, all local CPU execution.
Model managed by llm_profile.yaml → ModelManager.select("tts").

Caller: voice_pipeline.py
"""
from __future__ import annotations

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("aiplat.tts")
_DEFAULT_VOICE = "huayan"


async def sys_tts_generate(
    text: str,
    *,
    voice: str = _DEFAULT_VOICE,
    format: str = "wav",
    trace_context: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Generate speech audio from text via local Piper TTS.

    Returns raw audio bytes (WAV format).
    Zero network dependency — all local CPU execution.
    """
    from ._trace import trace_syscall_entry
    trace_syscall_entry("sys_tts_generate")

    if not text or not text.strip():
        return b""

    text = text[:2000]

    try:
        from core.harness.infrastructure.infra_audio_adapter import InfraAudioAdapter
        adapter = InfraAudioAdapter()
        wav_path = await adapter.synthesize(text, voice=voice)

        with open(wav_path, "rb") as f:
            audio_bytes = f.read()

        import os
        try:
            os.unlink(wav_path)
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

        logger.debug("TTS generated: %d chars → %d bytes (voice=%s)", len(text), len(audio_bytes), voice)
        return audio_bytes

    except Exception as e:
        logger.warning("TTS generation failed: %s", e)
        return b""
