"""
sys_tool - Tool syscall wrappers (Phase 2).

Centralizes tool invocation so future gates can be enforced here:
- PolicyGate (permission + approval)
- TraceGate (span + audit record)
- ResilienceGate (timeout/retry)
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, Optional

from core.harness.infrastructure.gates import PolicyGate, PolicyDecision, TraceGate, ContextGate, ResilienceGate
from core.harness.kernel.runtime import get_kernel_runtime
import time
from core.harness.interfaces import ToolResult
from core.harness.kernel.execution_context import get_active_workspace_context
from core.harness.kernel.execution_context import get_active_release_context


async def sys_tool_call(
    tool: Any,
    tool_args: Dict[str, Any],
    *,
    user_id: str = "system",
    session_id: str = "default",
    timeout_seconds: Optional[float] = None,
    trace_context: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    Execute a tool call.

    Notes:
    - Injects `_user_id` / `_session_id` into args for downstream wrappers.
    """
    policy_gate = PolicyGate()
    trace_gate = TraceGate()
    ctx_gate = ContextGate()
    res_gate = ResilienceGate()

    # Start span early so "fast-fail" (missing tool) is still observable.
    tool_name = str(getattr(tool, "name", None) or getattr(tool, "get_name", lambda: "")() or "")
    span = await trace_gate.start(
        "sys.tool.call",
        attributes={
            "tool": tool_name,
            "user_id": user_id,
            "trace_id": (trace_context or {}).get("trace_id") if isinstance(trace_context, dict) else None,
        },
    )
    start_ts = time.time()
    _ar = get_active_release_context()
    _run_id = (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None

    # Run events (best-effort): tool_start
    try:
        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        if store is not None and _run_id:
            await store.append_run_event(
                run_id=str(_run_id),
                event_type="tool_start",
                trace_id=span.trace_id,
                tenant_id=(trace_context or {}).get("tenant_id") if isinstance(trace_context, dict) else None,
                payload={
                    "tool": tool_name or "<unknown>",
                    "user_id": user_id,
                    "session_id": session_id,
                    "tenant_id": (trace_context or {}).get("tenant_id") if isinstance(trace_context, dict) else None,
                },
            )
    except Exception:
        pass

    if tool is None or not hasattr(tool, "execute"):
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
                        "kind": "tool",
                        "name": tool_name or "<unknown>",
                        "status": "failed",
                                "target_type": _ar.target_type if _ar else None,
                                "target_id": _ar.target_id if _ar else None,
                                "user_id": user_id,
                                "session_id": session_id,
                        "start_time": start_ts,
                        "end_time": end_ts,
                        "duration_ms": (end_ts - start_ts) * 1000.0,
                        "args": {"tool_args": tool_args or {}},
                        "error": "tool_not_executable",
                                "error_code": "TOOL_NOT_EXECUTABLE",
                    }
                )
            except Exception:
                pass
            try:
                if _run_id:
                    await store.append_run_event(
                        run_id=str(_run_id),
                        event_type="tool_end",
                        trace_id=span.trace_id,
                        tenant_id=(trace_context or {}).get("tenant_id") if isinstance(trace_context, dict) else None,
                        payload={"tool": tool_name or "<unknown>", "status": "failed", "error": "TOOL_NOT_EXECUTABLE"},
                    )
            except Exception:
                pass
        raise RuntimeError("Tool is not executable")

    args = dict(tool_args or {})
    # Tenant propagation for policy-as-code (best-effort).
    try:
        if isinstance(trace_context, dict) and trace_context.get("tenant_id") and "_tenant_id" not in args:
            args["_tenant_id"] = trace_context.get("tenant_id")
    except Exception:
        pass
    # Provide identity info for permission wrapper + auditing.
    args.setdefault("_user_id", user_id)
    args.setdefault("_session_id", session_id)
    # Provide tool risk metadata for approval/priority (best-effort).
    try:
        cfg = getattr(tool, "_config", None)
        meta = getattr(cfg, "metadata", None) if cfg else None
        if isinstance(meta, dict):
            if "risk_level" in meta:
                args.setdefault("_risk_level", meta.get("risk_level"))
            if "risk_weight" in meta:
                args.setdefault("_risk_weight", meta.get("risk_weight"))
            if meta.get("sensitive_operations") is not None:
                args.setdefault("_sensitive_operations", meta.get("sensitive_operations"))
            if meta.get("approval_required") is True:
                args.setdefault("_approval_required", True)
    except Exception:
        pass

    # P1-1: Exec backend gate (force approval for non-local execution backends).
    try:
        if tool_name == "code":
            from core.apps.exec_drivers.registry import get_exec_backend

            backend = await get_exec_backend()
            args.setdefault("_exec_backend", backend)
            if str(backend) and str(backend) != "local":
                args["_approval_required"] = True
    except Exception:
        pass

    # Phase R2: Toolset gate (runtime allowlist). Fail-closed when a toolset is active.
    try:
        ws = get_active_workspace_context()
        active_toolset = getattr(ws, "toolset", None) if ws else None
        if active_toolset:
            from core.harness.tools.toolsets import resolve_toolset, is_tool_allowed

            policy = resolve_toolset(str(active_toolset))
            allowed, reason = is_tool_allowed(policy, tool_name or "<unknown>", args)
            if not allowed:
                runtime = get_kernel_runtime()
                store = getattr(runtime, "execution_store", None) if runtime else None
                if store is not None:
                    try:
                        await store.add_syscall_event(
                            {
                                "trace_id": span.trace_id,
                                "span_id": getattr(span, "span_id", None),
                                "run_id": (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                                "kind": "tool",
                                "name": tool_name or "<unknown>",
                                "status": "toolset_denied",
                                "target_type": _ar.target_type if _ar else None,
                                "target_id": _ar.target_id if _ar else None,
                                "tenant_id": args.get("_tenant_id"),
                                "user_id": user_id,
                                "session_id": session_id,
                                "start_time": start_ts,
                                "end_time": start_ts,
                                "duration_ms": 0.0,
                                "args": {"tool_args": args, "toolset": policy.name},
                                "error": reason or "toolset_denied",
                                "error_code": "TOOLSET_DENIED",
                            }
                        )
                    except Exception:
                        pass
                await trace_gate.end(span, success=False)
                try:
                    runtime = get_kernel_runtime()
                    store = getattr(runtime, "execution_store", None) if runtime else None
                    if store is not None and _run_id:
                        await store.append_run_event(
                            run_id=str(_run_id),
                            event_type="tool_end",
                            trace_id=span.trace_id,
                            tenant_id=args.get("_tenant_id"),
                            payload={"tool": tool_name or "<unknown>", "status": "toolset_denied", "error": reason or "TOOLSET_DENIED"},
                        )
                except Exception:
                    pass
                return ToolResult(
                    success=False,
                    output=None,
                    error="toolset_denied",
                    metadata={"reason": reason, "tool": tool_name, "toolset": policy.name},
                )
    except Exception:
        # Best-effort: do not break existing behavior if toolset gate fails.
        pass

    # PolicyGate (permission; approval optional via env flag)
    pr = policy_gate.check_tool(user_id=user_id, tool_name=tool_name or "<unknown>", tool_args=args)
    if pr.decision == PolicyDecision.DENY:
        # Standardize as a ToolResult to avoid raising and to make approval/deny states machine-readable.
        # Also persist syscall event (best-effort).
        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        if store is not None:
            try:
                await store.add_syscall_event(
                    {
                        "trace_id": span.trace_id,
                        "span_id": getattr(span, "span_id", None),
                        "run_id": (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                        "kind": "tool",
                        "name": tool_name or "<unknown>",
                        "status": "policy_denied",
                        "target_type": _ar.target_type if _ar else None,
                        "target_id": _ar.target_id if _ar else None,
                        "tenant_id": getattr(pr, "tenant_id", None) or args.get("_tenant_id"),
                        "user_id": user_id,
                        "session_id": session_id,
                        "start_time": start_ts,
                        "end_time": start_ts,
                        "duration_ms": 0.0,
                        "args": {"tool_args": args},
                        "error": pr.reason or "policy_denied",
                        "error_code": "POLICY_DENIED",
                        "approval_request_id": pr.approval_request_id,
                    }
                )
            except Exception:
                pass
            try:
                # Audit (best-effort)
                await store.add_audit_log(
                    action="tool_policy_denied" if getattr(pr, "policy_version", None) else "tool_permission_denied",
                    status="denied",
                    tenant_id=getattr(pr, "tenant_id", None) or args.get("_tenant_id"),
                    actor_id=user_id,
                    resource_type="tool",
                    resource_id=tool_name or "<unknown>",
                    run_id=str(_run_id) if _run_id else None,
                    trace_id=span.trace_id,
                    detail={
                        "reason": pr.reason,
                        "policy_version": getattr(pr, "policy_version", None),
                    },
                )
            except Exception:
                pass
        await trace_gate.end(span, success=False)
        try:
            runtime = get_kernel_runtime()
            store = getattr(runtime, "execution_store", None) if runtime else None
            if store is not None and _run_id:
                await store.append_run_event(
                    run_id=str(_run_id),
                    event_type="tool_end",
                    trace_id=span.trace_id,
                    tenant_id=getattr(pr, "tenant_id", None) or args.get("_tenant_id"),
                    payload={
                        "tool": tool_name or "<unknown>",
                        "status": "policy_denied",
                        "error": pr.reason or "POLICY_DENIED",
                        "tenant_id": getattr(pr, "tenant_id", None) or args.get("_tenant_id"),
                        "policy_version": getattr(pr, "policy_version", None),
                    },
                )
        except Exception:
            pass
        return ToolResult(
            success=False,
            output=None,
            error="policy_denied",
            metadata={
                "reason": pr.reason,
                "tool": tool_name,
                "user_id": user_id,
                "tenant_id": getattr(pr, "tenant_id", None) or args.get("_tenant_id"),
                "policy_version": getattr(pr, "policy_version", None),
            },
        )
    if pr.decision == PolicyDecision.APPROVAL_REQUIRED:
        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        if store is not None:
            try:
                await store.add_syscall_event(
                    {
                        "trace_id": span.trace_id,
                        "span_id": getattr(span, "span_id", None),
                        "run_id": (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                        "kind": "tool",
                        "name": tool_name or "<unknown>",
                        "status": "approval_required",
                        "target_type": _ar.target_type if _ar else None,
                        "target_id": _ar.target_id if _ar else None,
                        "tenant_id": getattr(pr, "tenant_id", None) or args.get("_tenant_id"),
                        "user_id": user_id,
                        "session_id": session_id,
                        "start_time": start_ts,
                        "end_time": start_ts,
                        "duration_ms": 0.0,
                        "args": {"tool_args": args},
                        "result": {"approval_request_id": pr.approval_request_id},
                        "error": pr.reason or "approval_required",
                        "error_code": "APPROVAL_REQUIRED",
                        "approval_request_id": pr.approval_request_id,
                    }
                )
            except Exception:
                pass
            try:
                await store.add_audit_log(
                    action="tool_policy_approval_required" if getattr(pr, "policy_version", None) else "tool_approval_required",
                    status="approval_required",
                    tenant_id=getattr(pr, "tenant_id", None) or args.get("_tenant_id"),
                    actor_id=user_id,
                    resource_type="tool",
                    resource_id=tool_name or "<unknown>",
                    run_id=str(_run_id) if _run_id else None,
                    trace_id=span.trace_id,
                    detail={
                        "reason": pr.reason,
                        "approval_request_id": pr.approval_request_id,
                        "policy_version": getattr(pr, "policy_version", None),
                    },
                )
            except Exception:
                pass
        await trace_gate.end(span, success=False)
        try:
            runtime = get_kernel_runtime()
            store = getattr(runtime, "execution_store", None) if runtime else None
            if store is not None and _run_id:
                # Extra run event for long-poll /runs/{run_id}/wait consumers.
                try:
                    await store.append_run_event(
                        run_id=str(_run_id),
                        event_type="approval_requested",
                        trace_id=span.trace_id,
                        tenant_id=getattr(pr, "tenant_id", None) or args.get("_tenant_id"),
                        payload={
                            "kind": "tool",
                            "tool": tool_name or "<unknown>",
                            "approval_request_id": pr.approval_request_id,
                            "reason": pr.reason,
                            "policy_version": getattr(pr, "policy_version", None),
                        },
                    )
                except Exception:
                    pass
                await store.append_run_event(
                    run_id=str(_run_id),
                    event_type="tool_end",
                    trace_id=span.trace_id,
                    tenant_id=getattr(pr, "tenant_id", None) or args.get("_tenant_id"),
                    payload={
                        "tool": tool_name or "<unknown>",
                        "status": "approval_required",
                        "approval_request_id": pr.approval_request_id,
                        "error": pr.reason or "APPROVAL_REQUIRED",
                        "tenant_id": getattr(pr, "tenant_id", None) or args.get("_tenant_id"),
                        "policy_version": getattr(pr, "policy_version", None),
                    },
                )
        except Exception:
            pass
        return ToolResult(
            success=False,
            output=None,
            error="approval_required",
            metadata={
                "reason": pr.reason,
                "approval_request_id": pr.approval_request_id,
                "tool": tool_name,
                "user_id": user_id,
                "tenant_id": getattr(pr, "tenant_id", None) or args.get("_tenant_id"),
                "policy_version": getattr(pr, "policy_version", None),
            },
        )

    prepared_args = ctx_gate.prepare_tool_args(args, context=trace_context or {})

    async def _run():
        return await tool.execute(prepared_args)  # type: ignore[misc]

    try:
        retries = int(os.getenv("AIPLAT_TOOL_RETRIES", "0") or "0")
        result = await res_gate.run(_run, retries=retries, timeout_seconds=timeout_seconds)
        end_ts = time.time()
        await trace_gate.end(span, success=bool(getattr(result, "success", True)))
        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        if store is not None:
            try:
                status = "success" if bool(getattr(result, "success", True)) else "failed"
                if getattr(result, "error", None) == "approval_required":
                    status = "approval_required"
                elif getattr(result, "error", None) == "policy_denied":
                    status = "policy_denied"
                try:
                    if _run_id:
                        await store.append_run_event(
                            run_id=str(_run_id),
                            event_type="tool_end",
                            trace_id=span.trace_id,
                            tenant_id=prepared_args.get("_tenant_id") if isinstance(prepared_args, dict) else args.get("_tenant_id"),
                            payload={
                                "tool": tool_name or "<unknown>",
                                "status": status,
                                "error": getattr(result, "error", None),
                            },
                        )
                except Exception:
                    pass
                await store.add_syscall_event(
                    {
                        "trace_id": span.trace_id,
                        "span_id": getattr(span, "span_id", None),
                        "run_id": (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                        "kind": "tool",
                        "name": tool_name or "<unknown>",
                        "status": status,
                        "tenant_id": prepared_args.get("_tenant_id") if isinstance(prepared_args, dict) else args.get("_tenant_id"),
                        "user_id": user_id,
                        "session_id": session_id,
                        "start_time": start_ts,
                        "end_time": end_ts,
                        "duration_ms": (end_ts - start_ts) * 1000.0,
                        "args": {"tool_args": prepared_args},
                        "result": {"output": getattr(result, "output", None), "error": getattr(result, "error", None)},
                        "approval_request_id": prepared_args.get("_approval_request_id") if isinstance(prepared_args, dict) else None,
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
                try:
                    if _run_id:
                        await store.append_run_event(
                            run_id=str(_run_id),
                            event_type="tool_end",
                            trace_id=span.trace_id,
                            tenant_id=prepared_args.get("_tenant_id") if isinstance(prepared_args, dict) else args.get("_tenant_id"),
                            payload={"tool": tool_name or "<unknown>", "status": "failed", "error": "tool_error"},
                        )
                except Exception:
                    pass
                await store.add_syscall_event(
                    {
                        "trace_id": span.trace_id,
                        "span_id": getattr(span, "span_id", None),
                        "run_id": (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                        "kind": "tool",
                        "name": tool_name or "<unknown>",
                        "status": "failed",
                        "tenant_id": prepared_args.get("_tenant_id") if isinstance(prepared_args, dict) else args.get("_tenant_id"),
                        "user_id": user_id,
                        "session_id": session_id,
                        "start_time": start_ts,
                        "end_time": end_ts,
                        "duration_ms": (end_ts - start_ts) * 1000.0,
                        "args": {"tool_args": prepared_args},
                        "error": "tool_error",
                        "approval_request_id": prepared_args.get("_approval_request_id") if isinstance(prepared_args, dict) else None,
                    }
                )
            except Exception:
                pass
        raise
