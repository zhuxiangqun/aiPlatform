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
        import uuid as _uuid, time as _time
        plan = self._load_plan(agent, context)
        if not plan or not plan.steps:
            return await self._fallback.execute_agent(agent, context)

        # Extract/generate run_id from context
        ctx_vars = getattr(context, "variables", {}) or {}
        run_id = ctx_vars.get("_run_id") or getattr(context, "session_id", "") or f"graph-{_uuid.uuid4().hex[:12]}"
        graph_span_id = f"graph:{run_id}:start"

        # Emit graph_start root event for unified execution tree
        try:
            from core.services.execution_store import get_execution_store
            _es = get_execution_store()
            await _es.add_syscall_event({
                "id": f"{run_id}:graph_start",
                "parent_span_id": None,
                "kind": "pipeline",
                "name": "graph_start",
                "status": "running",
                "span_id": graph_span_id,
                "run_id": run_id,
                "start_time": _time.time(),
                "duration_ms": 0,
            })
        except Exception:
            pass

        results: Dict[str, Any] = {"steps": [], "plan": plan.to_dict()}
        for step in plan.steps:
            step.status = "in_progress"
            step_span_id = f"step:graph:{run_id}:{step.step}"
            # Emit step_start event
            try:
                from core.services.execution_store import get_execution_store
                _es = get_execution_store()
                await _es.add_syscall_event({
                    "id": f"{run_id}:step:{step.step}",
                    "span_id": step_span_id,
                    "parent_span_id": graph_span_id,
                    "kind": "step",
                    "name": f"step_{step.step}",
                    "status": "running",
                    "run_id": run_id,
                    "start_time": _time.time(),
                    "step_number": int(step.step) if str(step.step).isdigit() else 0,
                })
            except Exception:
                pass
            try:
                output = await self._exec_step(step, agent, context, run_id, step_span_id)
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

    async def _exec_step(self, step: PlanStep, agent: Any, context: Any, run_id: str = "", step_span_id: str = "") -> Any:
        kind = (step.kind or "instruction").lower()
        model = getattr(agent, "_model", None) if agent else None
        tc = {"run_id": run_id, "parent_span_id": step_span_id} if run_id else {}

        if kind == "tool":
            return await sys_tool_call(step.action, step.args, trace_context=tc or None)
        elif kind == "skill":
            return await sys_skill_call(step.action, step.args, trace_context=tc or None)
        elif kind == "llm":
            return await sys_llm_generate(model, str(step.action), trace_context={**tc, "source": "plan_engine", "step": str(step.step)} if tc else {"source": "plan_engine", "step": str(step.step)})
        else:
            return await self._fallback.execute_agent(agent, context)

    def _build_success_result(self, results: Dict[str, Any]) -> Any:
        from ...kernel.types import ExecutionResult as ER
        return ER(ok=True, payload=results)

    def _build_error_result(self, results: Dict[str, Any], error: str) -> Any:
        from ...kernel.types import ExecutionResult as ER
        return ER(ok=False, payload=results, error=error, http_status=500)
