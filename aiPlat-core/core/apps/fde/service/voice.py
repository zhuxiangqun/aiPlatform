"""
Voice Brainstorm — 语音漫谈意图提取服务.

接收 Whisper 转录文本，通过 LLM 提取核心意图、可执行步骤、待澄清模糊点。
"""
from __future__ import annotations

import json as _json
import logging
import os
import time as _time
from typing import Any, Dict

_log = logging.getLogger("aiplat.voice")


def _parse_llm_json(content: str) -> Dict[str, Any]:
    """从 LLM 响应中提取 JSON."""
    try:
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            parts = content.split("```")
            for p in parts:
                if p.strip().startswith("{"):
                    content = p
                    break
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            return _json.loads(content[start:end + 1])
    except Exception:
        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
    return {"core_intent": content[:500], "actionable_steps": [], "fuzzy_points": []}


def _store_emotion_state(session_id: str, data: Dict[str, Any]) -> None:
    """保留最近 10 条情绪状态."""
    try:
        tone = data.get("tone", "")
        style = data.get("response_style", {})
        if not tone:
            return
        emo_dir = os.path.expanduser("~/.aiplat/emotion")
        os.makedirs(emo_dir, exist_ok=True)
        emo_file = os.path.join(emo_dir, f"{session_id}.json")
        recent = []
        if os.path.exists(emo_file):
            try:
                with open(emo_file) as f:
                    recent = _json.load(f)
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
        recent.append({
            "tone": tone,
            "complexity": style.get("complexity", "standard"),
            "tone_adjust": style.get("tone_adjust", "neutral"),
            "timestamp": _time.time(),
        })
        with open(emo_file, "w") as f:
            _json.dump(recent[-10:], f)
    except Exception:
        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)


async def _trigger_conversation_ingest() -> None:
    """异步触发对话知识摄取."""
    try:
        import asyncio
        async def _ingest():
            from core.harness.knowledge.conversation_ingestor import ConversationIngestor
            ingestor = ConversationIngestor()
            await ingestor.ingest_recent(hours=1, max_messages=5)
        asyncio.ensure_future(_ingest())
    except Exception:
        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)


async def run_voice_brainstorm(
    transcript: str,
    duration_seconds: int,
    session_id: str = "default",
) -> Dict[str, Any]:
    """执行语音漫谈 LLM 意图提取.

    Args:
        transcript: Whisper 转录的原始文本（含口癖、自我纠正等）
        duration_seconds: 录音时长
        session_id: 当前会话 ID，用于情绪状态持久化

    Returns:
        {"success": bool, "summary": dict, "response_style": dict}
    """
    transcript = transcript.strip()
    if len(transcript) < 20:
        return {"success": False, "error": "转录文本过短 (需≥20字符)", "summary": {}}

    try:
        from core.harness.utils.model_injection import best_model_for_purpose
        from core.harness.utils.prompt_loader import _sync_resolve
        from core.harness.syscalls.llm import sys_llm_generate

        prompt = _sync_resolve(
            "voice-brainstorm",
            transcript=transcript[:8000],
            duration=str(duration_seconds)
        )

        result = await sys_llm_generate(
            messages=[{"role": "user", "content": prompt}],
            model=best_model_for_purpose("reasoning"),
            temperature=0.3,
            max_tokens=1500,
        )
        content = result.get("content", "") if isinstance(result, dict) else str(result)
        data = _parse_llm_json(content)

        # 后台异步触发会话知识摄取
        await _trigger_conversation_ingest()

        # 持久化情绪状态
        _store_emotion_state(session_id, data)

        return {
            "success": True,
            "duration_seconds": duration_seconds,
            "summary": data,
            "response_style": data.get("response_style", {}),
        }
    except Exception as e:
        _log.warning("brainstorm failed: %s", e)
        return {"success": False, "error": str(e)[:200], "summary": {}}
