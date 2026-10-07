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

import re

import io

from typing import AsyncIterator, Dict, Optional, Tuple



logger = logging.getLogger("aiplat.digital_human")
_LAST_CONSULTANT_MODEL = ""
_LAST_CONSULTANT_PURPOSE = ""


def _agent_timeout_sec() -> float:
    """LLM+RAG budget for digital-human turns (env-overridable)."""
    try:
        return max(15.0, float(os.getenv("AIPLAT_DIGITAL_HUMAN_TIMEOUT_SEC", "90")))
    except Exception:
        return 90.0


_NO_MODEL_USER_MSG = (
    "当前没有可用的对话模型。请先在「模型管理」启用至少一个聊天模型，再回来问我。"
)

_CONSULTANT_COT_HEAD = re.compile(
    r"(?m)^(?:#{1,6}\s*)?(?:步骤\s*\d+\s*[:：].*(?:分析|约束|解读|方案|比较|结论)|"
    r"可能的解读|方案比较)"
)


def _strip_consultant_cot(text: str) -> str:
    """Drop ReAct 步骤1–4 / 方案比较 so the user only sees the final reply."""
    raw = (text or "").strip()
    if not raw or not _CONSULTANT_COT_HEAD.search(raw[:2000]):
        return raw
    m = re.search(r"(?m)^(?:#{1,6}\s*)?步骤\s*\d+\s*[:：]\s*结论\s*$", raw)
    if m:
        rest = raw[m.end() :].lstrip(" \t\n-")
        if len(rest) > 40:
            return rest.strip()
    parts = re.split(r"\n-{3,}\s*\n", raw)
    if len(parts) >= 2 and _CONSULTANT_COT_HEAD.search(parts[0]):
        cand = parts[-1].strip()
        if len(cand) > 40:
            return cand
    return raw


def _rewrite_empty_model_answer(text: str) -> str:
    raw = (text or "").strip()
    if raw in ("No model available", "No model available for sys_llm_generate"):
        return _NO_MODEL_USER_MSG
    if "No model available" in raw and len(raw) < 80:
        return _NO_MODEL_USER_MSG
    return text


_ROLE_ACK = (
    "了解了你的角色",
    "了解了您的角色",
    "了解你的角色",
    "了解您的角色",
    "我会严格按照",
    "请告诉我用户的具体需求",
    "请提供用户的问题",
    "等待用户提问",
    "请把用户的问题发给我",
    "想做一个应用还是做一个",
    "做一个应用还是做一个agent",
    "做一个应用还是做一个 Agent",
    "请提供详细信息，我会根据平台实况",
    "根据您提供的信息和平台实况简报",
)


def _is_consultant_role_ack(text: str) -> bool:
    """True when the model answered the instruction block instead of the user."""
    raw = (text or "").strip()
    if not raw:
        return False
    return any(m in raw for m in _ROLE_ACK)


def _asks_app_vs_agent(question: str) -> bool:
    from core.harness.digital_human.platform_status_brief import asks_app_vs_agent

    return asks_app_vs_agent(question)


def _is_unasked_app_vs_agent_dump(answer: str, question: str) -> bool:
    if _asks_app_vs_agent(question):
        return False
    raw = (answer or "").strip()
    if not raw:
        return False
    markers = (
        "做应用 vs 做 Agent",
        "做应用 vs 做Agent",
        "#### 如何选择",
        "应用走 /app/factory",
        "请提供详细信息，我会根据平台实况",
    )
    if any(m in raw for m in markers):
        return True
    return False


def _consultant_user_payload(
    question: str,
    brief: str,
    dialogue: str = "",
    about: str = "",
    constitution: str = "",
    knowledge: str = "",
) -> str:
    """Question first; session; notes; constitution; on-demand pack; live brief."""
    q = (question or "").strip()
    d = (dialogue or "").strip()
    a = (about or "").strip()
    c = (constitution or "").strip()
    k = (knowledge or "").strip()
    b = (brief or "").strip()
    parts = [q]
    if d:
        parts.extend(["", "---", d])
    if a:
        parts.extend(["", "---", a])
    if c:
        parts.extend(["", "---", c])
    if k:
        parts.extend(["", "---", k])
    if b:
        parts.extend(["", "---", b])
    return "\n".join(parts).strip()


def _answer_from_injected_page(page_data: str) -> str:
    """Compact recap of live audit fields. Not an intent classifier."""
    from core.harness.digital_human.platform_status_brief import (
        _parse_page_data_fields,
        scrub_audit_english,
    )

    fields = _parse_page_data_fields(page_data)
    issues = []
    for i in range(8):
        val = scrub_audit_english(str(fields.get(f"issue{i}") or "").strip())
        if val:
            issues.append(val)
    if not issues:
        return ""
    skill = str(fields.get("skillId") or fields.get("skillName") or "").strip()
    summary = str(fields.get("auditSummary") or "").strip()
    who = f"Skill `{skill}`" if skill else "本页"
    blob = " ".join(issues)
    lines = [f"{who} 审核" + (f"（{summary}）" if summary else "") + "。"]
    if any(k in blob for k in ("unrealized_side_effect", "inferred:upload")):
        lines.append("结论：说会真上传，但是 prompt、没绑 Tool/MCP。一键修不了这条。")
        lines.append("要真传：去装名称含 oss/upload 的 Tool 或 MCP，回来勾选保存。不要真传：点「改成只出文案」。")
    else:
        for it in issues[:3]:
            lines.append(it)
    if any(k in blob for k in ("missing_keywords", "triggers_too_few")):
        lines.append("警告可点「应用」，不能代替上面的错误。保存后再点「AI 审核」。")
    else:
        lines.append("改完保存，再点「AI 审核」。")
    return "\n".join(lines)


def _consultant_model_meta(user_text: str = "") -> dict:
    """Infer purpose from the question, then infra unified_pipeline."""
    global _LAST_CONSULTANT_MODEL, _LAST_CONSULTANT_PURPOSE
    msgs = [{"role": "user", "content": user_text}] if (user_text or "").strip() else None
    meta: dict = {}
    try:
        from core.harness.utils.model_injection import best_model_for_purpose_with_meta

        raw = best_model_for_purpose_with_meta("auto", messages=msgs)
        if isinstance(raw, dict):
            meta = raw
    except Exception:
        logger.debug("consultant model auto-select failed", exc_info=True)
    _LAST_CONSULTANT_MODEL = str(meta.get("model") or "").strip()
    _LAST_CONSULTANT_PURPOSE = str(meta.get("model_purpose") or "").strip()
    return meta


def _consultant_selected_model(user_text: str = "") -> str:
    return str(_consultant_model_meta(user_text).get("model") or "").strip()


def _consultant_status_frame(user_text: str) -> dict:
    """Thinking frame carries model + inferred purpose for the 小朱 header."""
    meta = _consultant_model_meta(user_text)
    frame: dict = {"type": "status", "data": "thinking"}
    model = str(meta.get("model") or "").strip()
    purpose = str(meta.get("model_purpose") or "").strip()
    if model:
        frame["model"] = model
    if purpose:
        frame["purpose"] = purpose
    return frame


def _ensure_consultant_llm(agent: object, user_text: str = "") -> str:
    """Bind a real infra adapter. Workspace agents keep model: auto until execute."""
    if agent is None:
        return ""
    conv = getattr(agent, "_conv_config", None)
    cfg = getattr(agent, "_config", None)
    md = getattr(cfg, "metadata", None) if cfg is not None else None
    if conv is not None and isinstance(md, dict):
        sp = str(md.get("system_prompt") or "").strip()
        if sp:
            conv.system_prompt = sp

    if not hasattr(agent, "_model") and not hasattr(agent, "set_model"):
        return ""
    try:
        from core.harness.utils.model_injection import ensure_agent_model

        meta = _consultant_model_meta(user_text)
        name = str(meta.get("model") or "").strip()
        if not name:
            return ""
        cur = getattr(agent, "_model", None)
        cur_name = ""
        if cur is not None:
            cur_name = str(
                getattr(cur, "model_name", None)
                or getattr(cur, "_model_name", None)
                or ""
            ).strip()
        purpose = str(meta.get("model_purpose") or "auto")
        if cur is not None and cur_name == name:
            return name
        logger.warning(
            "consultant LLM bind purpose=%s model=%s (was %s)",
            purpose,
            name,
            cur_name or "none",
        )
        ensure_agent_model(agent, model_name=name, force=bool(cur is not None))
        return name
    except Exception:
        logger.debug("consultant LLM bind failed", exc_info=True)
        return ""




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





async def generate_answer(
    text: str,
    page_context="",
    session_id: str = "digital_human",
    page_data: str = "",
    tenant_id: str = "default",
) -> Tuple[str, bytes]:
    """Platform consultant (text) with live status brief; optional TTS.

    Prefer workspace agent ``platform_consultant``, fall back to ``materials_chat``.
    Injects a deterministic disk-scanned brief. TTS off by default
    (``AIPLAT_DIGITAL_HUMAN_TTS=true`` to enable).

    page_context: str (route) or dict {route, label, group, groupLabel}
    tenant_id: scopes personal notes (G9); sanitized to safe id
    Returns: (answer_text, tts_audio_bytes)
    """

    if not text.strip():
        return "", b""

    global _LAST_CONSULTANT_MODEL, _LAST_CONSULTANT_PURPOSE
    _LAST_CONSULTANT_MODEL = ""
    _LAST_CONSULTANT_PURPOSE = ""

    try:
        from core.harness.digital_human.consultant_personal import sanitize_tenant_id

        tenant_id = sanitize_tenant_id(tenant_id)
    except Exception:
        tenant_id = "default"

    import asyncio as _aio
    answer = ""
    brief = ""
    page_only_brief = False

    # Pure praise / short correction: rate prior turn; skip LLM for pure "讲得对"
    try:
        from core.harness.digital_human.trajectory_collector import (
            export_curated_sharegpt_dataset,
            infer_feedback_from_user,
            mark_feedback,
        )

        inferred_early = infer_feedback_from_user(text)
        if inferred_early and inferred_early.get("rating") == "good":
            mark_feedback(session_id, "good")
            export_curated_sharegpt_dataset(session_filter=session_id)
            collect_ack = "收到，这条我会记成可用样本。"
            try:
                from core.harness.digital_human.trajectory_collector import collect_turn

                collect_turn(session_id, "user", text)
                collect_turn(session_id, "assistant", collect_ack)
            except Exception:
                logger.debug("praise ack trajectory failed", exc_info=True)
            return collect_ack, b""
        if inferred_early and inferred_early.get("rating") == "bad":
            mark_feedback(
                session_id,
                "bad",
                correction=inferred_early.get("correction") or "",
            )
            export_curated_sharegpt_dataset(session_filter=session_id)
            # Continue to LLM so 小朱 can acknowledge + restate with correction in context
    except Exception:
        logger.debug("early feedback path failed", exc_info=True)

    try:
        from core.harness.digital_human.platform_status_brief import (
            build_platform_status_brief,
            is_inventory_question,
            use_page_only_brief,
        )
        page_only_brief = use_page_only_brief(text, page_data)
        brief = build_platform_status_brief(
            page_context=page_context,
            page_data=page_data,
            include_inventory=not page_only_brief,
            name_limit=0 if is_inventory_question(text) else 12,
        )
    except Exception:
        logger.debug("platform status brief failed", exc_info=True)

    try:
        from core.harness.meta.profile_registry import set_profile_override
        try:
            # Prefer consultant profile; fall back to digital_human if missing
            try:
                set_profile_override("platform_consultant", session_id=session_id)
            except Exception:
                set_profile_override("digital_human", session_id=session_id)
        except Exception:
            logger.debug("profile override failed", exc_info=True)

        from core.harness.integration import get_agent_registry as _get_discovery_registry
        from core.harness.interfaces import AgentContext

        registry = _get_discovery_registry()
        agent = registry.get("platform_consultant")
        agent_name = "platform_consultant"
        if agent is None:
            agent = registry.get("materials_chat")
            agent_name = "materials_chat"

        if agent is None:
            logger.warning("No consultant/materials_chat in registry — attempting materials_chat create")
            try:
                from core.api.core_facade import create_agent as _facade_create_agent
                from core.harness.interfaces import AgentConfig
                from core.harness.utils.model_injection import best_model_for_agent_type
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
                        timeout=int(_agent_timeout_sec()),
                        max_retries=2,
                        metadata={"name": "materials_chat", "agent_type": "materials_chat"},
                    ),
                )
                agent_name = "materials_chat"
            except Exception as e:
                logger.warning("Direct MaterialsChatAgent creation failed: %s", e)
                agent = None

        if agent is None:
            logger.warning("No agent available — echo fallback")
            answer = f"收到: {text}"
        else:
            run_ctx = {"entity_type": "平台咨询顾问", "priority": "normal"}
            if page_data:
                run_ctx["page_data"] = page_data
            if isinstance(page_context, dict):
                run_ctx["current_page"] = page_context.get("route", "")
                run_ctx["current_page_label"] = page_context.get("label", "")
                run_ctx["current_page_group"] = page_context.get("group", "")
                if page_context.get("purpose"):
                    run_ctx["current_page_purpose"] = page_context.get("purpose")
            elif page_context:
                run_ctx["current_page"] = page_context

            # Hot-reload AGENT.md SOP when disk mtime changes (G8)
            try:
                from core.harness.digital_human.consultant_reload import (
                    refresh_consultant_prompt,
                )

                if agent_name == "platform_consultant":
                    refresh_consultant_prompt(agent, agent_id="platform_consultant")
            except Exception:
                logger.debug("consultant AGENT.md reload failed", exc_info=True)

            bound_model = _ensure_consultant_llm(agent, text)
            _LAST_CONSULTANT_MODEL = bound_model or ""

            dialogue = ""
            try:
                from core.harness.digital_human.trajectory_collector import (
                    format_session_dialogue,
                    recent_session_turns,
                )

                dialogue = format_session_dialogue(recent_session_turns(session_id))
            except Exception:
                logger.debug("session dialogue load failed", exc_info=True)
            about = ""
            try:
                from core.harness.digital_human.consultant_personal import load_personal_notes

                about = load_personal_notes(tenant_id=tenant_id)
            except Exception:
                logger.debug("personal notes load failed", exc_info=True)
            constitution = ""
            knowledge = ""
            try:
                from core.harness.digital_human.consultant_knowledge import (
                    build_on_demand_pack,
                    load_constitution_card,
                )

                constitution = load_constitution_card()
                if not page_only_brief:
                    knowledge = build_on_demand_pack(text)
            except Exception:
                logger.debug("consultant knowledge pack failed", exc_info=True)
            user_payload = _consultant_user_payload(
                text, brief, dialogue, about, constitution, knowledge
            )

            ctx = AgentContext(
                session_id=session_id,
                user_id="system",
                messages=[{"role": "user", "content": user_payload}],
                variables={
                    "message": user_payload,
                    "tenant_id": tenant_id,
                    "scope": {
                        "doc_kinds": "all",
                        "collection_id": "system_docs",
                    },
                    "_run_context": run_ctx,
                    "_coding_policy_profile": "off",
                    "_skip_claude_md": True,
                    "platform_status_brief": brief,
                    "_consultant_agent": agent_name,
                },
            )

            try:
                result = await _aio.wait_for(agent.execute(ctx), timeout=_agent_timeout_sec())
                if result.success:
                    out = result.output
                    if isinstance(out, dict):
                        answer = (
                            out.get("answer")
                            or out.get("final_answer")
                            or out.get("text")
                            or ""
                        )
                    else:
                        answer = str(out or "")
                    answer = (answer or "").strip() or "收到。"
                    answer = _strip_consultant_cot(_rewrite_empty_model_answer(answer))
                    try:
                        from core.harness.digital_human.consultant_knowledge import (
                            ensure_generic_disclaimer,
                        )

                        answer = ensure_generic_disclaimer(
                            answer, text, page_only=page_only_brief
                        )
                    except Exception:
                        logger.debug("generic disclaimer failed", exc_info=True)
                else:
                    answer = result.error or "抱歉，我不太明白"
                    answer = _strip_consultant_cot(_rewrite_empty_model_answer(answer))
                    logger.warning("Agent returned error: %s", answer)
            except _aio.TimeoutError:
                answer = "抱歉，处理超时了，请稍后再试。"
                logger.warning("Agent execution timed out after %.0fs", _agent_timeout_sec())

    except Exception as e:
        logger.warning("Agent generation failed: %s", e)
        answer = "抱歉，处理出错了。"

    off_topic = page_only_brief and _is_unasked_app_vs_agent_dump(answer, text)
    if _is_consultant_role_ack(answer) or off_topic:
        facts = _answer_from_injected_page(page_data)
        if facts:
            answer = facts
            logger.warning("consultant answered role/off-topic factory; used page facts")
        elif _is_consultant_role_ack(answer):
            answer = (
                "当前页材料在，但我没有解读出审核卡片。"
                "请在本页再点一次「AI 审核」后问我。"
            )
            logger.warning("consultant answered role instructions; used page facts")

    # TTS opt-in (default off — 小朱 text-only)
    audio = b""
    _tts_on = os.getenv("AIPLAT_DIGITAL_HUMAN_TTS", "false").lower() in ("1", "true", "yes")
    if _tts_on and answer:
        try:
            import asyncio as _aio_tts
            from core.harness.syscalls.tts import sys_tts_generate
            audio = await _aio_tts.wait_for(sys_tts_generate(answer), timeout=20.0)
        except Exception:
            logger.warning("TTS failed or timed out — returning text-only answer", exc_info=True)

    try:
        from core.harness.digital_human.trajectory_collector import collect_turn

        collect_turn(session_id, "user", text)
        collect_turn(session_id, "assistant", answer)
    except Exception:
        logging.getLogger(__name__).debug("generate_answer trajectory failed", exc_info=True)
    try:
        from core.harness.digital_human.consultant_personal import remember_from_turn

        remember_from_turn(text, answer, tenant_id=tenant_id)
    except Exception:
        logging.getLogger(__name__).debug("personal remember failed", exc_info=True)

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
    conn_tenant = "default"

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
                if msg.get("tenant_id"):
                    try:
                        from core.harness.digital_human.consultant_personal import (
                            sanitize_tenant_id,
                        )

                        conn_tenant = sanitize_tenant_id(msg.get("tenant_id"))
                    except Exception:
                        conn_tenant = "default"
                if isinstance(ctx_data, dict) and ctx_data.get("data"):
                    conn_page_data = str(ctx_data["data"])[:1400]
                try:
                    meta = _consultant_model_meta("")
                    idle = {"type": "status", "data": "idle"}
                    if meta.get("model"):
                        idle["model"] = str(meta.get("model"))
                    if meta.get("model_purpose"):
                        idle["purpose"] = str(meta.get("model_purpose"))
                    if idle.get("model"):
                        await websocket.send_text(json.dumps(idle))
                except Exception:
                    logger.debug("consultant model chip on context failed", exc_info=True)

            elif msg_type == "feedback":
                if msg.get("session"):
                    conn_session = str(msg.get("session"))[:64]
                rating = str(msg.get("rating") or msg.get("data") or "").strip().lower()
                correction = str(msg.get("correction") or "").strip()
                try:
                    from core.harness.digital_human.trajectory_collector import (
                        export_curated_sharegpt_dataset,
                        mark_feedback,
                    )

                    result = mark_feedback(conn_session, rating, correction=correction)
                    if result.get("ok") and rating in ("good", "bad"):
                        export_curated_sharegpt_dataset(session_filter=conn_session)
                    await websocket.send_text(
                        json.dumps({"type": "feedback_ack", "ok": bool(result.get("ok")), **{k: v for k, v in result.items() if k != "ok"}})
                    )
                except Exception as e:
                    logger.debug("feedback mark failed", exc_info=True)
                    await websocket.send_text(
                        json.dumps({"type": "feedback_ack", "ok": False, "error": str(e)[:120]})
                    )

            elif msg_type == "text":

                user_text = msg.get("data", "")
                if msg.get("session"):
                    conn_session = str(msg.get("session"))[:64]
                if msg.get("tenant_id"):
                    try:
                        from core.harness.digital_human.consultant_personal import (
                            sanitize_tenant_id,
                        )

                        conn_tenant = sanitize_tenant_id(msg.get("tenant_id"))
                    except Exception:
                        conn_tenant = "default"

                try:
                    await websocket.send_text(json.dumps(_consultant_status_frame(user_text)))
                except Exception:  # noqa: cleanup-best-effort
                    pass

                answer, audio = await generate_answer(
                    user_text,
                    page_context,
                    session_id=conn_session,
                    page_data=conn_page_data,
                    tenant_id=conn_tenant,
                )

                # Send text immediately so UI unlocks even if audio is empty
                resp = {
                    "type": "answer",
                    "text": answer,
                    "audio": base64.b64encode(audio).decode() if audio else "",
                    "format": "wav",
                    "model": _LAST_CONSULTANT_MODEL,
                }
                if _LAST_CONSULTANT_PURPOSE:
                    resp["purpose"] = _LAST_CONSULTANT_PURPOSE
                await websocket.send_text(json.dumps(resp))



            elif msg_type == "end":

                # Finalize audio buffer and transcribe

                audio_bytes = audio_buffer.getvalue()

                if audio_bytes:

                    text = await transcribe(audio_bytes)

                    await websocket.send_text(json.dumps({"type": "text", "data": text}))

                    if text:
                        try:
                            await websocket.send_text(json.dumps(_consultant_status_frame(text)))
                        except Exception:  # noqa: cleanup-best-effort
                            pass
                        answer, audio = await generate_answer(
                            text,
                            page_context,
                            session_id=conn_session,
                            page_data=conn_page_data,
                            tenant_id=conn_tenant,
                        )
                        resp = {
                            "type": "answer",
                            "text": answer,
                            "audio": base64.b64encode(audio).decode() if audio else "",
                            "format": "wav",
                            "model": _LAST_CONSULTANT_MODEL,
                        }
                        if _LAST_CONSULTANT_PURPOSE:
                            resp["purpose"] = _LAST_CONSULTANT_PURPOSE
                        await websocket.send_text(json.dumps(resp))



    except Exception as e:

        logger.warning("Voice chat handler error: %s", e)

        try:

            await websocket.send_text(json.dumps({"type": "error", "data": str(e)[:200]}))

        except Exception:

            logging.getLogger(__name__).debug('voice_chat_handler failed', exc_info=True)

    finally:

        # 会话结束：优先导出已评分/纠正的策展样本（噪音全量导出留给手动 export_sharegpt_dataset）。
        # 同时确保 FineTune 种子包存在（idempotent；已有文件则跳过）。
        try:
            from core.harness.digital_human.trajectory_collector import (
                export_curated_sharegpt_dataset,
                export_seed_sharegpt_dataset,
            )

            export_curated_sharegpt_dataset(session_filter=conn_session)
            export_seed_sharegpt_dataset()
        except Exception:
            logging.getLogger(__name__).debug('trajectory export failed', exc_info=True)
