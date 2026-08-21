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

        # P1-3 修复: 前端 MediaRecorder 录的是 audio/webm（Chrome/Firefox），但临时文件
        # 一直用 .wav 后缀 → 解码器被扩展名误导。按字节魔数嗅探真实容器格式：
        #   webm/ogg/opus: 0x1A 0x45 0xDF 0xA3 (EBML)
        #   wav: RIFF....WAVE
        _suffix = ".wav"
        if audio_bytes[:4] == b"\x1a\x45\xdf\xa3":
            _suffix = ".webm"
        elif audio_bytes[:4] == b"OggS":
            _suffix = ".ogg"

        with tempfile.NamedTemporaryFile(suffix=_suffix, delete=False) as tmp:

            tmp.write(audio_bytes)

            tmp_path = tmp.name



        # Use the adapter's transcribe method

        if hasattr(whisper, "transcribe"):

            result = whisper.transcribe(tmp_path)

            # P0-2 修复: InfraAudioAdapter.transcribe 返回 List[Dict]（segment 列表），
            # 之前用 str(result) 会把整个列表序列化成 "[{'start_ms': ...}, ...]" 垃圾文本。
            # 正确做法: 按时间顺序拼接各 segment 的文本。
            if isinstance(result, list):
                text = "".join(
                    str(seg.get("text", "") or "") for seg in result
                    if isinstance(seg, dict)
                )
            elif isinstance(result, dict):
                text = str(result.get("text", "") or "")
            else:
                text = str(result or "")

        else:

            text = ""



        os.unlink(tmp_path)

        return text.strip() if text else ""



    except Exception as e:

        logger.warning("Transcription failed: %s", e)

        return ""





async def generate_answer(text: str, page_context = "", session_id: str = "digital_human", page_data: str = "") -> Tuple[str, bytes]:
    """Send text to MaterialsChatAgent, get answer + TTS audio.
    
    page_context: str (old format: route path) or dict (new format: {route, label, group, groupLabel})
    
    Returns: (answer_text, tts_audio_bytes)
    """

    if not text.strip():
        return "", b""

    import asyncio as _aio

    try:

        # P1-1 修复: 应用数字人专属 ControlProfile（口语化/中高温/宽松门控，control_presets.yaml）
        from core.harness.meta.profile_registry import set_profile_override

        try:
            set_profile_override("digital_human", session_id=session_id)
        except Exception:
            logger.debug("profile override failed", exc_info=True)

        # P0-1 修复: 统一走 integration 入口（CoreFacade 同源，line 3079 re-export）。
        # integration.get_agent_registry 现在返回 discovery 模块级单例（DI 工厂修复，
        # server 启动时 AgentManager._bridge_to_registry 把 workspace agents 注册进该单例）。
        # 此前 DI 解析 lambda 工厂 TypeError → fallback 空实例，materials_chat 恒 None → echo。
        from core.harness.integration import get_agent_registry as _get_discovery_registry

        registry = _get_discovery_registry()

        agent = registry.get("materials_chat")

        if agent is None:
            # 兜底: 单例未初始化时经 CoreFacade.create_agent 创建（harness 不直导 apps）
            logger.warning("MaterialsChatAgent not in registry — attempting direct creation")
            try:
                from core.api.core_facade import create_agent as _facade_create_agent
                from core.harness.interfaces import AgentConfig
                from core.harness.utils.model_injection import best_model_for_agent_type

                # 模型解析可能因环境无可用模型抛错；此时传空 model，由 agent 内部默认解析。
                try:
                    _model = best_model_for_agent_type("materials_chat")
                except Exception as _e:
                    logger.warning("Model resolution failed (%s) — using empty model name", _e)
                    _model = ""

                agent = _facade_create_agent(
                    agent_type="materials_chat",
                    config=AgentConfig(
                        name="materials_chat",
                        model=_model,
                        temperature=0.4,
                        max_tokens=2000,
                        timeout=30,
                        max_retries=2,
                        metadata={"name": "materials_chat", "agent_type": "materials_chat"},
                    ),
                )
                logger.info("MaterialsChatAgent created directly (registry empty)")
            except Exception as e:
                logger.warning("Direct MaterialsChatAgent creation failed: %s", e)
                agent = None

        if agent is None:

            logger.warning("MaterialsChatAgent not available — using echo fallback")

            answer = f"收到: {text}"

        else:

            from core.harness.interfaces import AgentContext

            run_ctx = {"entity_type": "数字人助手", "priority": "normal"}
            if page_data:
                run_ctx["page_data"] = page_data
            if isinstance(page_context, dict):
                run_ctx["current_page"] = page_context.get("route", "")
                run_ctx["current_page_label"] = page_context.get("label", "")
                run_ctx["current_page_group"] = page_context.get("group", "")
            elif page_context:
                run_ctx["current_page"] = page_context

            ctx = AgentContext(
                session_id=session_id,
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

        collect_turn(session_id, "user", text)

        collect_turn(session_id, "assistant", answer)

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

        {"type": "answer", "text": "answer", "audio": "<base64 wav>", "format": "wav"}

        {"type": "error", "data": "..."}

    """

    import base64



    audio_buffer = io.BytesIO()
    page_context = ""
    conn_session = session_id
    conn_page_data = ""



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
                if msg.get("session"):
                    conn_session = str(msg.get("session"))[:64]
                if isinstance(ctx_data, dict) and ctx_data.get("data"):
                    conn_page_data = str(ctx_data["data"])[:800]

            elif msg_type == "text":

                user_text = msg.get("data", "")

                answer, audio = await generate_answer(user_text, page_context, session_id=conn_session, page_data=conn_page_data)

                resp = {

                    "type": "answer",

                    "text": answer,

                    "audio": base64.b64encode(audio).decode() if audio else "",

                    "format": "wav",  # P1-3: TTS 实际输出格式（Piper WAV），前端按此设置播放 MIME

                }

                await websocket.send_text(json.dumps(resp))



            elif msg_type == "end":

                # Finalize audio buffer and transcribe

                audio_bytes = audio_buffer.getvalue()

                if audio_bytes:

                    text = await transcribe(audio_bytes)

                    await websocket.send_text(json.dumps({"type": "text", "data": text}))

                    if text:

                        answer, audio = await generate_answer(text, page_context, session_id=conn_session, page_data=conn_page_data)

                        resp = {

                            "type": "answer",

                            "text": answer,

                            "audio": base64.b64encode(audio).decode() if audio else "",

                            "format": "wav",  # P1-3: TTS 实际输出格式（Piper WAV）

                        }

                        await websocket.send_text(json.dumps(resp))



    except Exception as e:

        logger.warning("Voice chat handler error: %s", e)

        try:

            await websocket.send_text(json.dumps({"type": "error", "data": str(e)[:200]}))

        except Exception:

            logging.getLogger(__name__).debug('voice_chat_handler failed', exc_info=True)

    finally:

        # P1-2 闭环: 会话结束（含异常）时把轨迹聚合导出为 ShareGPT 数据集，
        # 落入 ~/.aiplat/training/sft_digital_human_*.jsonl 供 SFT 训练消费。
        try:
            from core.harness.digital_human.trajectory_collector import export_sharegpt_dataset
            export_sharegpt_dataset()
        except Exception:
            logging.getLogger(__name__).debug('trajectory export failed', exc_info=True)
