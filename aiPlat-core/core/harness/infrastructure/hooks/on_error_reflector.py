"""
OnErrorReflector — 执行中实时反思 Hook (Phase 4.1)

当 Agent 连续工具调用失败时，自动触发轻量级 LLM 反思，修正策略后
继续执行。避免 Agent 撞墙失败。

触发条件: 连续 2 次 tool_call 返回 error
重试上限: 2 次反思
环境变量: AIPLAT_REFLECTOR_ENABLED=true (默认启用)
"""

from __future__ import annotations

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

    @property
    def name(self) -> str:
        return "OnErrorReflector"

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

        if is_error:
            self._consecutive_errors += 1
            _log.debug(f"OnErrorReflector: consecutive_errors={self._consecutive_errors}")

            if self._consecutive_errors >= 2 and self._reflect_count < self._max_reflect_retries:
                self._reflect_count += 1
                self._consecutive_errors = 0

                hint = await self._generate_reflection(context)
                if hint:
                    _log.info(f"OnErrorReflector: injected reflection hint ({self._reflect_count}/{self._max_reflect_retries})")
                    return {"reasoning_hint": hint}
        else:
            self._consecutive_errors = 0  # Reset on success

        # Reset reflect count on new task
        task = getattr(context, "task", "")
        if hasattr(self, "_last_task") and task != self._last_task:
            self._reflect_count = 0
        self._last_task = task

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


# ── Factory ─────────────────────────────────────────────────────────────

def create_on_error_reflector() -> OnErrorReflector:
    return OnErrorReflector()
