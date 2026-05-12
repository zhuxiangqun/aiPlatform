"""
PlanEngine (Phase 9).

Consumes ExecutionPlan from agent.context, executing steps sequentially.
Falls back to LoopEngine when no plan is available.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ...syscalls import sys_llm_generate, sys_tool_call, sys_skill_call
from ...kernel.types import ExecutionPlan, ExecutionResult, PlanStep
from .loop_engine import LoopEngine


class PlanEngine:
    name = "plan"

    def __init__(self, fallback: Optional[LoopEngine] = None):
        self._fallback = fallback or LoopEngine()

    async def execute_agent(self, agent: Any, context: Any) -> Any:
        plan = self._load_plan(agent, context)
        if not plan or not plan.steps:
            return await self._fallback.execute_agent(agent, context)

        results: Dict[str, Any] = {"steps": [], "plan": plan.to_dict()}
        for step in plan.steps:
            step.status = "in_progress"
            try:
                output = await self._exec_step(step, agent, context)
                step.status = "completed"
                results["steps"].append({"step": step.step, "status": "completed", "output": str(output)[:8000]})
            except Exception as e:
                step.status = "failed"
                results["steps"].append({"step": step.step, "status": "failed", "error": str(e)[:500]})
                return self._build_error_result(results, str(e))
            plan.advance()

        return self._build_success_result(results)

    def _load_plan(self, agent: Any, context: Any) -> Optional[ExecutionPlan]:
        ctx = getattr(agent, "context", {}) if agent else {}
        if isinstance(ctx, dict):
            raw = ctx.get("_execution_plan")
            if isinstance(raw, dict) and raw.get("steps"):
                return ExecutionPlan(
                    version=str(raw.get("version", "9.0")),
                    explain=str(raw.get("explain", "")),
                    steps=[PlanStep(**s) for s in raw.get("steps", [])],
                    current_step=int(raw.get("current_step", 0)),
                    metadata=dict(raw.get("metadata", {}) or {}),
                )
        return None

    async def _exec_step(self, step: PlanStep, agent: Any, context: Any) -> Any:
        kind = (step.kind or "instruction").lower()
        model = getattr(agent, "_model", None) if agent else None

        if kind == "tool":
            return await sys_tool_call(step.action, step.args)
        elif kind == "skill":
            return await sys_skill_call(step.action, step.args)
        elif kind == "llm":
            return await sys_llm_generate(model, str(step.action), trace_context={"source": "plan_engine", "step": step.step})
        else:
            return await self._fallback.execute_agent(agent, context)

    def _build_success_result(self, results: Dict[str, Any]) -> Any:
        from ...kernel.types import ExecutionResult as ER
        return ER(ok=True, payload=results)

    def _build_error_result(self, results: Dict[str, Any], error: str) -> Any:
        from ...kernel.types import ExecutionResult as ER
        return ER(ok=False, payload=results, error=error, http_status=500)
