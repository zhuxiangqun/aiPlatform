"""
sys_skill - Skill syscall wrappers (Phase 2).

Centralizes skill invocation so future gates can be enforced here:
- TraceGate (span + audit record)
- ResilienceGate (timeout/retry)
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, Optional

from ..interfaces import SkillContext
from core.harness.infrastructure.gates import TraceGate, ContextGate, ResilienceGate
from core.harness.kernel.runtime import get_kernel_runtime
import time


async def sys_skill_call(
    skill: Any,
    params: Dict[str, Any],
    *,
    context: Optional[SkillContext] = None,
    user_id: str = "system",
    session_id: str = "default",
    timeout_seconds: Optional[float] = None,
    trace_context: Optional[Dict[str, Any]] = None,
) -> Any:
    """Execute a skill call."""
    if skill is None or not hasattr(skill, "execute"):
        raise RuntimeError("Skill is not executable")

    trace_gate = TraceGate()
    ctx_gate = ContextGate()
    res_gate = ResilienceGate()

    ctx = context or SkillContext(session_id=session_id, user_id=user_id, variables=params or {})
    prepared_params = ctx_gate.prepare_tool_args(params or {}, context=trace_context or {})

    async def _run():
        return await skill.execute(ctx, prepared_params)  # type: ignore[misc]

    skill_name = str(getattr(skill, "name", None) or getattr(getattr(skill, "_config", None), "name", "") or "")
    span = await trace_gate.start(
        "sys.skill.call",
        attributes={
            "skill": skill_name,
            "trace_id": (trace_context or {}).get("trace_id") if isinstance(trace_context, dict) else None,
        },
    )
    start_ts = time.time()
    try:
        retries = int(os.getenv("AIPLAT_SKILL_RETRIES", "0") or "0")
        result = await res_gate.run(_run, retries=retries, timeout_seconds=timeout_seconds)
        end_ts = time.time()
        await trace_gate.end(span, success=bool(getattr(result, "success", True)))
        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        if store is not None:
            try:
                await store.add_syscall_event(
                    {
                        "trace_id": span.trace_id,
                        "span_id": getattr(span, "span_id", None),
                        "run_id": (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                        "kind": "skill",
                        "name": skill_name or "<unknown>",
                        "status": "success" if bool(getattr(result, "success", True)) else "failed",
                        "start_time": start_ts,
                        "end_time": end_ts,
                        "duration_ms": (end_ts - start_ts) * 1000.0,
                        "args": {"params": prepared_params},
                        "result": {"output": getattr(result, "output", None), "error": getattr(result, "error", None)},
                    }
                )
            except Exception:
                pass
        return result
    except Exception:
        end_ts = time.time()
        await trace_gate.end(span, success=False)
        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        if store is not None:
            try:
                await store.add_syscall_event(
                    {
                        "trace_id": span.trace_id,
                        "span_id": getattr(span, "span_id", None),
                        "run_id": (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                        "kind": "skill",
                        "name": skill_name or "<unknown>",
                        "status": "failed",
                        "start_time": start_ts,
                        "end_time": end_ts,
                        "duration_ms": (end_ts - start_ts) * 1000.0,
                        "args": {"params": prepared_params},
                        "error": "skill_error",
                    }
                )
            except Exception:
                pass
        raise
