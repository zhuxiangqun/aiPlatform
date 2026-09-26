"""
OnErrorReflector — 执行中实时反思 Hook (Phase 4.1)

当 Agent 连续工具调用失败时，自动触发轻量级 LLM 反思，修正策略后
继续执行。避免 Agent 撞墙失败。

触发条件: 连续 2 次 tool_call 返回 error
重试上限: 2 次反思
环境变量: AIPLAT_REFLECTOR_ENABLED=true (默认启用)
"""

from __future__ import annotations
import logging

import asyncio
import os, logging
from typing import Any, Dict, Optional

_log = logging.getLogger("aiplat.reflector")


class OnErrorReflector:
    """PostObserve 拦截点 — 连续工具失败时触发 LLM 反思。

    注册方式:
        hook_registry.register("PostObserve", OnErrorReflector(), priority=10)
    """

    def __init__(self):
        self._consecutive_errors: int = 0
        self._max_reflect_retries: int = 2
        self._reflect_count: int = 0
        self._enabled = os.getenv("AIPLAT_REFLECTOR_ENABLED", "true").lower() not in ("0", "false", "no")
        self._streak_tool: str = ""
        self._streak_error: str = ""
        self._last_task: str = ""

    @property
    def name(self) -> str:
        return "OnErrorReflector"

    @staticmethod
    def _tool_name(context: Any, tool_result: Any) -> str:
        for src in (tool_result, context):
            if src is None:
                continue
            name = getattr(src, "tool_name", None) or getattr(src, "name", None)
            if name:
                return str(name)
            if isinstance(src, dict):
                for key in ("tool_name", "name", "tool", "action_id"):
                    if src.get(key):
                        return str(src[key])
        return "tool"

    @staticmethod
    def _error_code(tool_result: Any, context: Any) -> str:
        err = getattr(tool_result, "error", None)
        if isinstance(tool_result, dict):
            err = err or tool_result.get("error") or tool_result.get("error_code")
        if isinstance(err, dict):
            return str(err.get("code") or err.get("type") or err)[:80]
        if err:
            return str(err)[:80]
        last = getattr(context, "last_error", None)
        return str(last or "error")[:80]

    async def on_post_observe(self, context: Any) -> Optional[Dict[str, Any]]:
        """PostObserve 拦截点。

        Args:
            context: HookContext, 包含 tool_result / task / last_error

        Returns:
            None (正常继续) 或 {"reasoning_hint": str} (注入反思建议)
        """
        if not self._enabled:
            return None

        # Check if tool call failed
        tool_result = getattr(context, "tool_result", None)
        if not tool_result:
            return None

        is_error = getattr(tool_result, "error", None) or (isinstance(tool_result, dict) and tool_result.get("error"))
        task = getattr(context, "task", "") or ""
        if hasattr(self, "_last_task") and task != self._last_task:
            self._reflect_count = 0
            self._consecutive_errors = 0
            self._streak_tool = ""
            self._streak_error = ""
        self._last_task = task

        if is_error:
            tool = self._tool_name(context, tool_result)
            err = self._error_code(tool_result, context)
            # K4: consecutive only counts same tool + same error class within this Run/task
            if tool == self._streak_tool and err == self._streak_error:
                self._consecutive_errors += 1
            else:
                self._streak_tool = tool
                self._streak_error = err
                self._consecutive_errors = 1
            _log.debug(f"OnErrorReflector: consecutive_errors={self._consecutive_errors} tool={tool}")

            if self._consecutive_errors >= 2 and self._reflect_count < self._max_reflect_retries:
                self._reflect_count += 1
                # keep streak identity; reset count after firing case+hint once
                streak_n = self._consecutive_errors
                self._consecutive_errors = 0

                if streak_n >= 2:
                    try:
                        from core.apps.fde.service.k_wave_case import record_case_from_tool_streak

                        record_case_from_tool_streak(
                            domain_id=str(getattr(context, "domain_id", "") or ""),
                            tool_name=tool,
                            error_code=err,
                            run_id=str(getattr(context, "run_id", "") or ""),
                            trace_id=str(getattr(context, "trace_id", "") or ""),
                            task=str(task)[:300],
                            detail=str(getattr(context, "last_error", "") or err)[:400],
                        )
                    except Exception:
                        _log.debug("K4 tool streak case skipped", exc_info=True)

                hint = await self._generate_reflection(context)
                if hint:
                    _log.info(f"OnErrorReflector: injected reflection hint ({self._reflect_count}/{self._max_reflect_retries})")
                    # ── Self-iteration loop: trigger AutoLearner on persistent errors ──
                    if self._reflect_count >= 2:
                        asyncio.create_task(self._trigger_auto_learner(context))
                    return {"reasoning_hint": hint}
        else:
            self._consecutive_errors = 0  # Reset on success
            self._streak_tool = ""
            self._streak_error = ""

        return None

    async def _generate_reflection(self, context: Any) -> Optional[str]:
        """调用 LLM 轻量级反思，生成修正建议。

        用最少的 token 生成 1-2 句策略修正。
        """
        try:
            from core.harness.syscalls.llm import sys_llm_generate
            task = getattr(context, "task", "")[:300]
            last_error = getattr(context, "last_error", "") or "未知错误"
            recent_actions = getattr(context, "recent_actions", [])[-3:]

            prompt = (
                "你是一个自反思 Agent。以下工具调用连续失败，请用最多 20 个字建议修正策略。\n\n"
                f"任务: {task}\n"
                f"最近操作: {recent_actions}\n"
                f"错误: {last_error}\n\n"
                "修正建议:"
            )
            resp = await sys_llm_generate(
                None, [{"role": "user", "content": prompt}],
                temperature=0.1, max_tokens=30,
            )
            hint = getattr(resp, "content", "") or str(resp)
            return hint.strip() if hint.strip() else None
        except Exception:
            return None

    async def _trigger_auto_learner(self, context: Any):
        """Self-iteration loop: persistent errors → AutoLearner draft generation."""
        try:
            from core.harness.learning import get_auto_learner
            learner = get_auto_learner()
            _log.info("OnErrorReflector: triggering AutoLearner for self-iteration")
            await learner.process_pending(min_confidence=0.6)
        except Exception as e:
            logging.debug(str(e), exc_info=True)


# ── Factory ─────────────────────────────────────────────────────────────

def create_on_error_reflector() -> OnErrorReflector:
    return OnErrorReflector()
