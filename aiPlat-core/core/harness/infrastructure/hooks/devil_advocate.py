"""
DevilAdvocate — PRE_ACT Hook: pre-execution risk analysis.

Before executing a high-risk action, simulates possible failure modes
and injects a warning into the agent's context. Complements the
post-action OnErrorReflector to form a complete "pre-check → execute → reflect" loop.

Trigger: PRE_ACT hook phase (loop.py:596)
Filter: only high-risk tools (file_write, code_exec, database, shell_exec, browser)
Cost: lightweight LLM call (3 questions, ~200 tokens) — skipped on trivial actions

Env vars:
  AIPLAT_DEVIL_ADVOCATE_ENABLED=true   (default: true)
  AIPLAT_DA_RISK_THRESHOLD=3           (1-5, ≥threshold → inject warning)
"""

from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional

_log = logging.getLogger("aiplat.devil_advocate")


class DevilAdvocate:
    """PRE_ACT Hook — 执行前模拟失败场景，预判风险。

    Registration:
        hook_manager.register(DevilAdvocate(), phase=HookPhase.PRE_ACT, priority=20)
    """

    # High-risk tool patterns that trigger pre-execution analysis
    HIGH_RISK_TOOLS = {
        "file_write", "file_edit", "file_delete",
        "code_execution", "code_exec", "shell_exec", "execute",
        "database", "database_query", "database_write",
        "browser", "browser_open",
    }

    def __init__(self):
        self._enabled = os.getenv("AIPLAT_DEVIL_ADVOCATE_ENABLED", "true").lower() in ("1", "true", "yes")
        self._threshold = int(os.getenv("AIPLAT_DA_RISK_THRESHOLD", "3"))

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ── Risk detection ──────────────────────────────

    def _is_risky(self, tool_name: str) -> bool:
        """Check if this tool type warrants pre-execution analysis."""
        return tool_name.lower() in self.HIGH_RISK_TOOLS

    def _extract_planned_action(self, state: dict) -> Optional[str]:
        """Extract the current planned action from state.

        Dual-path: PlanExecute mode uses explicit plan[], ReAct mode uses reasoning.
        Falls back gracefully — never blocks the main loop.
        """
        try:
            ctx = state.get("context", state)

            # Path 1: PlanExecute mode — explicit plan
            plan = ctx.get("plan", [])
            if plan and isinstance(plan, list):
                current = plan[0] if plan else {}
                desc = str(current.get("action", current.get("step", "")))
                if desc:
                    return desc
            if isinstance(plan, dict):
                return str(plan.get("action", str(plan)[:200]))

            # Path 2: ReAct mode — from last reasoning
            reasoning = ctx.get("_last_reasoning", "")
            if reasoning:
                return str(reasoning)[:300]

            # Path 3: No plan data — skip safely
            return None
        except Exception:
            return None

    # ── Main hook ───────────────────────────────────

    async def analyze(self, tool_name: str, planned_action: str,
                      state: Optional[dict] = None) -> Dict[str, Any]:
        """Analyze risks before executing a high-risk action.

        Returns: {"risk_level": 0-5, "warning": str, "mitigation": str}
        risk_level ≥ threshold → warning should be injected.
        """
        if not self._enabled:
            return {"risk_level": 0, "warning": "", "mitigation": ""}

        try:
            prompt = (
                f"Before executing this action, identify the top risks:\n\n"
                f"Tool: {tool_name}\n"
                f"Planned action: {planned_action[:200]}\n\n"
                f"Answer 3 questions in JSON format:\n"
                f'{{"failure_mode":"most likely failure if this step fails",\n'
                f' "irreversible":"any irreversible side effects (or none)",\n'
                f' "safer_alternative":"a safer approach (or none)",\n'
                f' "risk_level":1-5 (5=highly risky)}}'
            )

            analysis = await self._quick_llm(prompt)
            risk_level = int(analysis.get("risk_level", 1))
            warning = ""
            if risk_level >= self._threshold:
                warning = (
                    f"⚠ Devil's Advocate: {analysis.get('failure_mode', 'Unknown risk')}. "
                    f"Irreversible: {analysis.get('irreversible', 'none')}. "
                    f"Safer: {analysis.get('safer_alternative', 'proceed with caution')}."
                )
            return {
                "risk_level": risk_level,
                "warning": warning,
                "mitigation": analysis.get("safer_alternative", ""),
            }
        except Exception:
            return {"risk_level": 0, "warning": "", "mitigation": ""}

    async def _quick_llm(self, prompt: str) -> Dict[str, Any]:
        """Lightweight LLM call via existing model injection."""
        try:
            from core.harness.utils.model_injection import get_default_model
            from core.harness.syscalls.llm import sys_llm_generate

            model = get_default_model("doc")
            if not model:
                return {"risk_level": 1, "failure_mode": "no model available",
                        "irreversible": "none", "safer_alternative": "none"}

            resp = await sys_llm_generate(
                model, prompt, temperature=0.0, max_tokens=150,
            )
            content = getattr(resp, "content", str(resp) if isinstance(resp, str) else "")
            import json
            # Extract JSON from response
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        return {"risk_level": 1, "failure_mode": "analysis unavailable",
                "irreversible": "none", "safer_alternative": "none"}

    async def on_pre_act(self, tool_name: str, tool_args: dict = None,
                         state: dict = None) -> Dict[str, Any]:
        """Hook entry point — called before every tool execution.

        Returns a hint dict to inject into agent context, or empty dict.
        Never blocks — always returns immediately.
        """
        if not self._enabled:
            return {"continue": True}

        # Only trigger for high-risk tools
        if not self._is_risky(tool_name):
            return {"continue": True}

        planned = self._extract_planned_action(state or {})
        if not planned:
            return {"continue": True}

        # Run risk analysis
        risk = await self.analyze(tool_name, planned, state)

        hint = {}
        if risk["risk_level"] >= self._threshold:
            hint = {
                "warning": risk["warning"],
                "mitigation": risk.get("mitigation", ""),
                "risk_level": risk["risk_level"],
            }
            _log.info(f"DevilAdvocate: risk={risk['risk_level']}/{self._threshold} "
                      f"tool={tool_name}")

        return hint


_devil_advocate: Optional[DevilAdvocate] = None


def get_devil_advocate() -> DevilAdvocate:
    global _devil_advocate
    if _devil_advocate is None:
        _devil_advocate = DevilAdvocate()
    return _devil_advocate
