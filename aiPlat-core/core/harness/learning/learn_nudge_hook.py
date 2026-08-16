"""
Learn Nudge Hook — 会话内实时学习触发 (P1-A1, Hermes 借鉴)

AutoLearner 从"夜间批量"升级为"实时触发":
  - 每 N 次 POST_OBSERVE 或 stage 失败, 后台调用 AutoLearner.analyze_failure/analyze_success
  - 轻量计数阈值: AIPLAT_LEARN_NUDGE_INTERVAL (默认 10 次观察)
  - 只对失败观察生成草稿 (成功观察仅统计, 不写草稿 — 控制 token)
  - 后台 asyncio.create_task, 不阻塞 ReActLoop 热路径
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger("aiplat.learn_nudge")

_NUDGE_INTERVAL = int(os.getenv("AIPLAT_LEARN_NUDGE_INTERVAL", "10"))
_NUDGE_ERROR_KEYWORDS = ("error:", "failed", "exception", "traceback",
                         "tool_error", "command not found", "permission denied")


def _is_error_observation(obs: Any) -> bool:
    if not isinstance(obs, str):
        return False
    low = obs.lower()
    return any(kw in low for kw in _NUDGE_ERROR_KEYWORDS)


def _needs_review(draft: Any) -> bool:
    """Lightweight gate: skip drafts with halved confidence (rejected-before)."""
    return getattr(draft, "confidence", 0) >= 0.6


async def _run_nudge(agent_id: str, run_id: str, task: str, error: str,
                     suggested_fix: str = "", is_failure: bool = True) -> None:
    """Background nudge: analyze → gate → submit draft."""
    try:
        from core.harness.learning import AutoLearner
        learner = AutoLearner()
        if is_failure:
            draft = learner.analyze_failure(
                error, agent_id=agent_id, run_id=run_id, task=task,
                suggested_fix=suggested_fix)
        else:
            draft = learner.analyze_success(task, agent_id=agent_id, run_id=run_id)
        if not draft:
            return
        if not _needs_review(draft):
            logger.debug("nudge skipped draft (confidence %.2f)", draft.confidence)
            return
        learner.submit_for_review(draft)
        logger.info("learn_nudge: draft submitted agent=%s run=%s name=%s conf=%.2f",
                    agent_id, run_id, draft.name, draft.confidence)
    except Exception as e:
        logger.debug("learn_nudge failed: %s", e, exc_info=True)


def create_learn_nudge_hook():
    """Create the learn-nudge hook (POST_OBSERVE phase, low priority)."""
    async def learn_nudge_hook(context):
        try:
            ctx = context.state or {}
            observations = ctx.get("_observations") or []
            if not observations:
                return {"continue": True}

            # Counter: nudge every N observations
            if len(observations) % _NUDGE_INTERVAL != 0:
                return {"continue": True}

            recent = observations[-1]
            is_failure = _is_error_observation(recent)
            if not is_failure:
                # Success path: only nudge every 5 intervals (lightweight stats)
                return {"continue": True}

            agent_id = str(ctx.get("agent_id") or ctx.get("_agent_id") or "")
            run_id = str(ctx.get("run_id") or ctx.get("_run_id") or "")
            task = str(ctx.get("task") or ctx.get("goal") or ctx.get("prompt") or "")
            error = recent[:500]

            # Fire-and-forget background task — never block the hot path
            asyncio.ensure_future(_run_nudge(
                agent_id=agent_id, run_id=run_id, task=task, error=error,
                suggested_fix=str(ctx.get("_reflection_hint") or ""),
            ))
        except Exception as e:
            logger.debug("learn_nudge hook error: %s", e, exc_info=True)
        return {"continue": True}

    from core.harness.infrastructure.hooks.hook_manager import HookPhase, create_hook
    return create_hook(
        name="learn_nudge",
        callback=learn_nudge_hook,
        phase=HookPhase.POST_OBSERVE,
        priority=10,  # after on_error_reflector (45), lowest priority last
    )
