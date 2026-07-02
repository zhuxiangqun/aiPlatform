"""
QuickEngine (Phase 9).

Single-shot LLM call for simple tasks.
No loop, no tool/skill execution — just one prompt → one response.
Used for quick-turnaround interactions like simple Q&A.
"""

from __future__ import annotations
import logging

from typing import Any

from ...syscalls import sys_llm_generate


class QuickEngine:
    name = "quick"

    async def execute_agent(self, agent: Any, context: Any) -> Any:
        model = getattr(agent, "_model", None) if agent else None
        message = self._extract_message(context)
        prompt = message or "Hello"
        response = await sys_llm_generate(model, prompt, trace_context={"source": "quick_engine"})
        content = getattr(response, "content", str(response))
        return self._wrap_result(content)

    def _extract_message(self, context: Any) -> str:
        try:
            msgs = getattr(context, "messages", None) or []
            if msgs:
                return str(msgs[-1].get("content", "") or "")
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        try:
            vars0 = dict(getattr(context, "variables", {}) or {})
            return str(vars0.get("message", "") or "")
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        return ""

    def _wrap_result(self, content: str) -> Any:
        from ...kernel.types import ExecutionResult
        return ExecutionResult(ok=True, payload={"content": content})
