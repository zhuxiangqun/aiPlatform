"""

Voice Pipeline — ASR → Agent → TTS orchestration.



Reuses existing infra:

  - Whisper via InfraAudioAdapter (already wired in transcriber.py)

  - MaterialsChatAgent (already wired with RAG + 本体 + 记忆)

  - sys_tts_generate (new syscall, Edge TTS backend)

"""

from __future__ import annotations



import asyncio

import json

import logging

import os

import io

from typing import AsyncIterator, Dict, Optional, Tuple



logger = logging.getLogger("aiplat.digital_human")



# Cache Whisper model to avoid reloading per request

_whisper_model = None

_model_lock = asyncio.Lock()





async def _get_whisper():

    """Lazy-load Whisper model via InfraAudioAdapter."""

    global _whisper_model

    if _whisper_model is not None:

        return _whisper_model



    async with _model_lock:

        if _whisper_model is not None:

            return _whisper_model

        try:

            from core.harness.infrastructure.base_model_adapter import create_adapter

            adapter = create_adapter("audio")

            _whisper_model = adapter

        except Exception as e:

            logger.warning("Whisper adapter not available: %s", e)

            _whisper_model = False  # sentinel

        return _whisper_model





async def transcribe(audio_bytes: bytes) -> str:

    """Convert audio bytes to text using Whisper via InfraAudioAdapter."""

    whisper = await _get_whisper()

    if not whisper:

        return ""



    try:

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:

            tmp.write(audio_bytes)

            tmp_path = tmp.name



        # Use the adapter's transcribe method

        if hasattr(whisper, "transcribe"):

            result = whisper.transcribe(tmp_path)

            text = result.get("text", "") if isinstance(result, dict) else str(result)

        else:

            text = ""



        os.unlink(tmp_path)

        return text.strip() if text else ""



    except Exception as e:

        logger.warning("Transcription failed: %s", e)

        return ""





async def generate_answer(text: str, page_context = "") -> Tuple[str, bytes]:
    """Send text to MaterialsChatAgent, get answer + TTS audio.
    
    page_context: str (old format: route path) or dict (new format: {route, label, group, groupLabel})
    
    Returns: (answer_text, tts_audio_bytes)
    """

    if not text.strip():
        return "", b""

    import asyncio as _aio

    try:

        from core.harness.meta.profile_registry import set_profile_override

        from core.harness.integration import get_agent_registry  # P0-A1: DI 解析

        registry = get_agent_registry()

        agent = registry.get("materials_chat")

        if agent is None:

            logger.warning("MaterialsChatAgent not available — using echo fallback")

            answer = f"收到: {text}"

        else:

            from core.harness.interfaces import AgentContext

            run_ctx = {"entity_type": "数字人助手", "priority": "normal"}
            if isinstance(page_context, dict):
                run_ctx["current_page"] = page_context.get("route", "")
                run_ctx["current_page_label"] = page_context.get("label", "")
                run_ctx["current_page_group"] = page_context.get("group", "")
            elif page_context:
                run_ctx["current_page"] = page_context

            ctx = AgentContext(
                session_id="digital_human",
                user_id="system",
                variables={
                    "message": text,
                    "tenant_id": "default",
                    "scope": {
                        "doc_kinds": "all",
                        "collection_id": "system_docs",
                    },
                    "_run_context": run_ctx,
                },
            )

            try:

                result = await _aio.wait_for(agent.execute(ctx), timeout=30.0)

                if result.success:

                    answer = result.output.get("answer", "") or "收到。"

                else:

                    answer = result.error or "抱歉，我不太明白"

                    logger.warning("Agent returned error: %s", answer)

            except _aio.TimeoutError:

                answer = "抱歉，处理超时了，请稍后再试。"

                logger.warning("Agent execution timed out after 30s")



    except Exception as e:

        logger.warning("Agent generation failed: %s", e)

        answer = f"抱歉，处理出错了。"



    # Generate TTS audio

    from core.harness.syscalls.tts import sys_tts_generate

    audio = await sys_tts_generate(answer)



    # A: Collect trajectory for fine-tuning

    try:

        from core.harness.digital_human.trajectory_collector import collect_turn

        collect_turn("dh_session", "user", text)

        collect_turn("dh_session", "assistant", answer)

    except Exception:

        logging.getLogger(__name__).debug('generate_answer failed', exc_info=True)


    return answer, audio





async def voice_chat_handler(websocket, session_id: str = "digital_human"):

    """WebSocket handler: receive audio chunks → return { text, audio_base64 }.



    Protocol (JSON over WebSocket):

      Client sends:

        {"type": "audio", "data": "<base64 audio chunk>"}

        {"type": "text", "data": "hello"}

        {"type": "end"}  — signals end of audio stream



      Server sends:

        {"type": "text", "data": "transcribed text"}

        {"type": "answer", "text": "answer", "audio": "<base64 mp3>"}

        {"type": "error", "data": "..."}

    """

    import base64



    audio_buffer = io.BytesIO()
    page_context = ""



    try:

        async for raw in websocket.iter_text():

            try:

                msg = json.loads(raw)

            except json.JSONDecodeError:

                await websocket.send_text(json.dumps({"type": "error", "data": "invalid json"}))

                continue



            msg_type = msg.get("type", "")



            if msg_type == "audio":

                data = msg.get("data", "")

                if data:

                    audio_buffer.write(base64.b64decode(data))



            elif msg_type == "context":
                ctx_data = msg.get("data", "")
                if isinstance(ctx_data, dict):
                    page_context = ctx_data
                else:
                    page_context = ctx_data

            elif msg_type == "text":

                user_text = msg.get("data", "")

                answer, audio = await generate_answer(user_text, page_context)

                resp = {

                    "type": "answer",

                    "text": answer,

                    "audio": base64.b64encode(audio).decode() if audio else "",

                }

                await websocket.send_text(json.dumps(resp))



            elif msg_type == "end":

                # Finalize audio buffer and transcribe

                audio_bytes = audio_buffer.getvalue()

                if audio_bytes:

                    text = await transcribe(audio_bytes)

                    await websocket.send_text(json.dumps({"type": "text", "data": text}))

                    if text:

                        answer, audio = await generate_answer(text, page_context)

                        resp = {

                            "type": "answer",

                            "text": answer,

                            "audio": base64.b64encode(audio).decode() if audio else "",

                        }

                        await websocket.send_text(json.dumps(resp))



    except Exception as e:

        logger.warning("Voice chat handler error: %s", e)

        try:

            await websocket.send_text(json.dumps({"type": "error", "data": str(e)[:200]}))

        except Exception:

            logging.getLogger(__name__).debug('voice_chat_handler failed', exc_info=True)
