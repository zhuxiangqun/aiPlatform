"""

sys_tts — Text-to-Speech syscall (Edge TTS backend).



Uses Microsoft Edge TTS (free, no API key required, good Chinese voice quality).

Complies with syscall boundary: all external calls go through sys_* functions.

"""

from __future__ import annotations



import asyncio

import logging

import tempfile

from typing import Optional, Dict, Any



logger = logging.getLogger("aiplat.tts")



# Default voice: Chinese female, natural tone

_DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"





async def sys_tts_generate(

    text: str,

    *,

    voice: str = _DEFAULT_VOICE,

    format: str = "mp3",

    trace_context: Optional[Dict[str, Any]] = None,

) -> bytes:

    """Generate speech audio from text via Edge TTS.



    Returns raw audio bytes (MP3 format).

    Follows syscall boundary: trace_id + span_id + observability.

    """

    from ._trace import trace_syscall_entry

    trace_syscall_entry("sys_tts_generate")



    if not text or not text.strip():

        return b""



    text = text[:2000]  # Cap at 2000 chars (Edge TTS has a text length limit)



    try:

        import edge_tts



        with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as tmp:

            tmp_path = tmp.name



        communicate = edge_tts.Communicate(text, voice)

        await communicate.save(tmp_path)



        with open(tmp_path, "rb") as f:

            audio_bytes = f.read()



        import os

        try:

            os.unlink(tmp_path)

        except Exception:

            logging.getLogger(__name__).debug('sys_tts_generate failed', exc_info=True)


        logger.debug("TTS generated: %d chars → %d bytes", len(text), len(audio_bytes))

        return audio_bytes



    except Exception as e:

        logger.warning("TTS generation failed: %s", e)

        return b""

