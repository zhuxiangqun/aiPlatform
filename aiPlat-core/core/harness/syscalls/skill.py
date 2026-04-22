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
from core.harness.infrastructure.gates import TraceGate, ContextGate, ResilienceGate, PolicyGate, PolicyDecision
from core.harness.kernel.runtime import get_kernel_runtime
import time
from core.harness.kernel.execution_context import get_active_release_context, get_active_request_context
from core.apps.tools.skill_tools import resolve_executable_skill_permission


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
    trace_gate = TraceGate()
    ctx_gate = ContextGate()
    res_gate = ResilienceGate()
    policy_gate = PolicyGate()

    # Start span early so "fast-fail" (missing skill) is still observable.
    skill_name = str(getattr(skill, "name", None) or getattr(getattr(skill, "_config", None), "name", "") or "")
    span = await trace_gate.start(
        "sys.skill.call",
        attributes={
            "skill": skill_name,
            "trace_id": (trace_context or {}).get("trace_id") if isinstance(trace_context, dict) else None,
        },
    )
    start_ts = time.time()
    _ar = get_active_release_context()
    _pr = get_active_request_context()

    if skill is None or not hasattr(skill, "execute"):
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
                        "target_type": _ar.target_type if _ar else None,
                        "target_id": _ar.target_id if _ar else None,
                        "tenant_id": getattr(_pr, "tenant_id", None),
                        "user_id": user_id,
                        "session_id": session_id,
                        "start_time": start_ts,
                        "end_time": end_ts,
                        "duration_ms": (end_ts - start_ts) * 1000.0,
                        "args": {"params": params or {}},
                        "error": "skill_not_executable",
                        "error_code": "SKILL_NOT_EXECUTABLE",
                    }
                )
            except Exception:
                pass
        raise RuntimeError("Skill is not executable")

    ctx = context or SkillContext(session_id=session_id, user_id=user_id, variables=params or {})
    prepared_params = ctx_gate.prepare_tool_args(params or {}, context=trace_context or {})

    # ---- P1: executable skill governance (deny/ask/allow + approval) ----
    try:
        if os.getenv("AIPLAT_ENFORCE_EXECUTABLE_SKILL_POLICY", "true").lower() in ("1", "true", "yes", "y"):
            # propagate identity/run
            args = dict(prepared_params or {})
            args.setdefault("_user_id", user_id)
            args.setdefault("_session_id", session_id)
            try:
                if isinstance(trace_context, dict) and trace_context.get("tenant_id") and "_tenant_id" not in args:
                    args["_tenant_id"] = trace_context.get("tenant_id")
            except Exception:
                pass
            try:
                if isinstance(trace_context, dict) and trace_context.get("run_id") and "_run_id" not in args:
                    args["_run_id"] = str(trace_context.get("run_id"))
            except Exception:
                pass
            try:
                arq = get_active_request_context()
                if arq and getattr(arq, "actor_role", None):
                    args.setdefault("_actor_role", getattr(arq, "actor_role"))
            except Exception:
                pass

            # Basic permission posture for executable skills
            decision = resolve_executable_skill_permission(skill_name)
            if decision == "deny":
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
                                "status": "policy_denied",
                                "target_type": _ar.target_type if _ar else None,
                                "target_id": _ar.target_id if _ar else None,
                                "tenant_id": getattr(_pr, "tenant_id", None),
                                "user_id": user_id,
                                "session_id": session_id,
                                "start_time": start_ts,
                                "end_time": end_ts,
                                "duration_ms": (end_ts - start_ts) * 1000.0,
                                "args": {"params": args},
                                "error": f"executable_skill_denied:{skill_name}",
                                "error_code": "EXEC_SKILL_DENIED",
                            }
                        )
                    except Exception:
                        pass
                # Return a structured result instead of raising (so loop can handle it).
                from core.harness.interfaces import SkillResult

                return SkillResult(success=False, output=None, error="policy_denied", metadata={"reason": "exec_skill_denied", "skill": skill_name})
            if decision == "ask":
                args["_approval_required"] = True

            # Require explicit permissions declaration unless disabled
            require_perm = os.getenv("AIPLAT_EXEC_SKILL_REQUIRE_PERMISSIONS", "true").lower() in ("1", "true", "yes", "y")
            if require_perm:
                try:
                    cfg = getattr(skill, "_config", None)
                    meta = getattr(cfg, "metadata", None) if cfg else None
                    perms = []
                    if isinstance(meta, dict):
                        perms = meta.get("permissions") or meta.get("permission") or []
                    if isinstance(perms, str):
                        perms = [perms]
                    if not isinstance(perms, list) or not [p for p in perms if str(p).strip()]:
                        args["_approval_required"] = True  # fail-safe: require approval if permissions are missing
                        args.setdefault("_policy_reason", "missing_permissions")
                except Exception:
                    args["_approval_required"] = True
                    args.setdefault("_policy_reason", "missing_permissions")

            # PolicyGate approval flow (mirrors sys_tool_call behavior)
            pr = policy_gate.check_skill(user_id=user_id, skill_name=skill_name or "<unknown>", skill_args=args)
            if pr.decision == PolicyDecision.DENY:
                from core.harness.interfaces import SkillResult

                return SkillResult(success=False, output=None, error="policy_denied", metadata={"reason": pr.reason, "skill": skill_name})
            if pr.decision == PolicyDecision.APPROVAL_REQUIRED:
                from core.harness.interfaces import SkillResult

                return SkillResult(
                    success=False,
                    output=None,
                    error="approval_required",
                    metadata={"approval_request_id": pr.approval_request_id, "reason": pr.reason, "skill": skill_name},
                )

            prepared_params = args
    except Exception:
        # Fail-open for compatibility
        pass

    async def _run():
        return await skill.execute(ctx, prepared_params)  # type: ignore[misc]

    # (span already started above)
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
                        "target_type": _ar.target_type if _ar else None,
                        "target_id": _ar.target_id if _ar else None,
                        "tenant_id": getattr(_pr, "tenant_id", None),
                        "user_id": user_id,
                        "session_id": session_id,
                        "start_time": start_ts,
                        "end_time": end_ts,
                        "duration_ms": (end_ts - start_ts) * 1000.0,
                        "args": {"params": prepared_params},
                        "result": {"output": getattr(result, "output", None), "error": getattr(result, "error", None)},
                        "error_code": "SKILL_FAILED" if not bool(getattr(result, "success", True)) else None,
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
                        "target_type": _ar.target_type if _ar else None,
                        "target_id": _ar.target_id if _ar else None,
                        "tenant_id": getattr(_pr, "tenant_id", None),
                        "user_id": user_id,
                        "session_id": session_id,
                        "start_time": start_ts,
                        "end_time": end_ts,
                        "duration_ms": (end_ts - start_ts) * 1000.0,
                        "args": {"params": prepared_params},
                        "error": "skill_error",
                        "error_code": "SKILL_ERROR",
                    }
                )
            except Exception:
                pass
        raise
