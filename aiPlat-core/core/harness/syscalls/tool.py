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
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from core.harness.infrastructure.gates import PolicyGate, PolicyDecision, TraceGate, ContextGate, ResilienceGate
from core.harness.kernel.runtime import get_kernel_runtime
import time
from core.harness.interfaces import ToolResult
from core.harness.kernel.execution_context import get_active_workspace_context
from core.harness.kernel.execution_context import get_active_release_context
from core.harness.kernel.execution_context import get_active_tenant_policy_context


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
    coding_profile = (
        str((trace_context or {}).get("coding_policy_profile") or "off").strip().lower()
        if isinstance(trace_context, dict)
        else "off"
    )

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
    # Fallback tenant propagation from active request context.
    try:
        if "_tenant_id" not in args:
            from core.harness.kernel.execution_context import get_active_request_context

            arq = get_active_request_context()
            if arq and getattr(arq, "tenant_id", None):
                args["_tenant_id"] = getattr(arq, "tenant_id")
    except Exception:
        pass
    # PR-08: persist run_id for approval replay/links (best-effort).
    try:
        _run_id = (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None
        if _run_id and "_run_id" not in args:
            args["_run_id"] = str(_run_id)
    except Exception:
        pass
    # Fallback run_id: for nested calls, session_id is often the run_id.
    try:
        if "_run_id" not in args and isinstance(session_id, str) and session_id.startswith(("run_", "run-")):
            args["_run_id"] = str(session_id)
    except Exception:
        pass
    # Provide identity info for permission wrapper + auditing.
    args.setdefault("_user_id", user_id)
    args.setdefault("_session_id", session_id)
    # Carry profile for observability/debugging (best-effort).
    if coding_profile and "_coding_policy_profile" not in args:
        args["_coding_policy_profile"] = coding_profile
    # Provide actor_role for policy engine (best-effort).
    try:
        from core.harness.kernel.execution_context import get_active_request_context

        arq = get_active_request_context()
        if arq and getattr(arq, "actor_role", None):
            args.setdefault("_actor_role", getattr(arq, "actor_role"))
    except Exception:
        pass
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

    # P4: approval layering policy (skill-only / sensitive-only)
    # If a parent skill has already been approved, we can reuse the same approval_request_id
    # for nested tool calls to avoid double-approval when configured.
    try:
        approval_layer_policy = str(os.getenv("AIPLAT_APPROVAL_LAYER_POLICY", "both") or "both").strip().lower()
        tool_force_list = os.getenv("AIPLAT_APPROVAL_TOOL_FORCE_LIST", "").strip()
        # Tenant policy override
        try:
            tpol = get_active_tenant_policy_context()
            pol0 = getattr(tpol, "policy", None) if tpol else None
            layer = pol0.get("approval_layering") if isinstance(pol0, dict) else None
            if isinstance(layer, dict):
                if isinstance(layer.get("policy"), str) and layer.get("policy").strip():
                    approval_layer_policy = str(layer.get("policy")).strip().lower()
                if isinstance(layer.get("tool_force_list"), str):
                    tool_force_list = str(layer.get("tool_force_list")).strip()
        except Exception:
            pass
        if approval_layer_policy in {"skill_only", "tool_only", "skill_then_tool_sensitive_only"}:
            from core.harness.kernel.execution_context import get_active_approval_request_id
            import fnmatch

            arid = get_active_approval_request_id()
            if isinstance(arid, str) and arid and "_approval_request_id" not in args:
                # Sensitive-only: do NOT reuse approval for tools in force list (they must request their own approval).
                if approval_layer_policy == "skill_then_tool_sensitive_only":
                    patterns = [p.strip() for p in str(tool_force_list or "").split(",") if p.strip()]
                    op = f"tool:{tool_name}"
                    if patterns and any(fnmatch.fnmatch(op, pat) for pat in patterns):
                        arid = None
                if isinstance(arid, str) and arid:
                    args["_approval_request_id"] = str(arid)
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

    # P0: repo-aware workflow gate (force approval for mutating git operations).
    try:
        if tool_name == "repo":
            op = args.get("operation") or args.get("op")
            if str(op) in {"add", "unstage", "restore", "commit", "checkout", "branch_create", "reset", "revert"}:
                args["_approval_required"] = True
                # Provide an explicit reason for approvals UI (best-effort).
                args.setdefault("_policy_reason", "repo_mutation_requires_approval")
                # Stronger guard under karpathy_v1: disallow broad add without explicit paths.
                if coding_profile == "karpathy_v1":
                    if str(op) == "add":
                        paths = args.get("paths") if isinstance(args.get("paths"), list) else None
                        broad = (not paths) or any(str(p).strip() in {".", "*"} for p in (paths or []))
                        if broad:
                            args.setdefault("_policy_reason", "repo_add_broad")
                            args["_approval_required"] = True

                # Attach a lightweight status snapshot (changed files) to help diff review in approvals.
                try:
                    repo_root = args.get("repo_root")
                    if not repo_root:
                        try:
                            from core.harness.kernel.execution_context import get_active_workspace_context

                            ws = get_active_workspace_context()
                            repo_root = getattr(ws, "repo_root", None) if ws else None
                        except Exception:
                            repo_root = None
                    cwd = Path(str(repo_root)) if repo_root else Path.cwd()
                    if cwd.exists() and cwd.is_dir() and shutil.which("git"):
                        p = subprocess.run(
                            ["git", "status", "--porcelain=v1"],
                            cwd=str(cwd),
                            capture_output=True,
                            text=True,
                            timeout=3,
                        )
                        if p.returncode in (0, 1):
                            lines = [ln for ln in (p.stdout or "").splitlines() if ln.strip()]
                            files = []
                            for ln in lines[:200]:
                                # "XY path" or "?? path"
                                parts = ln.split(maxsplit=1)
                                if len(parts) == 2:
                                    files.append(parts[1].strip())
                            args.setdefault("_repo_status_count", len(files))
                            args.setdefault("_repo_status_files", files[:50])
                except Exception:
                    pass

                # Diff Gate (Phase-2): compare repo status against declared change contract from coding skill output.
                try:
                    from core.harness.kernel.execution_context import get_active_change_contract

                    contract = get_active_change_contract()
                    if contract is not None:
                        args.setdefault("_declared_changed_files", list(contract.changed_files or [])[:50])
                        if contract.unrelated_changes is not None:
                            args.setdefault("_declared_unrelated_changes", bool(contract.unrelated_changes))
                        declared = set([str(x).strip() for x in (contract.changed_files or []) if str(x).strip()])
                        # Only enforce when contract explicitly claims no unrelated changes.
                        if contract.unrelated_changes is False and declared:
                            actual = set([str(x).strip() for x in (args.get("_repo_status_files") or []) if str(x).strip()])
                            extra = sorted(list(actual - declared))
                            if extra:
                                args["_approval_required"] = True
                                args["_policy_reason"] = "changed_files_out_of_contract"
                                args["_out_of_contract_files"] = extra[:20]
                            # If user asks repo add with explicit paths, ensure they are within declared set.
                            if str(op) == "add":
                                paths = args.get("paths") if isinstance(args.get("paths"), list) else []
                                # ignore broad markers (handled above)
                                chk = [str(p).strip() for p in paths if str(p).strip() and str(p).strip() not in {".", "*"}]
                                bad = sorted([p for p in chk if p not in declared])
                                if bad:
                                    args["_approval_required"] = True
                                    args["_policy_reason"] = "repo_add_paths_out_of_contract"
                                    args["_out_of_contract_files"] = bad[:20]
                except Exception:
                    pass
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
    try:
        # Unit tests / internal calls may not set request context. In that case, fail-open
        # so pure harness tests can execute dummy tools without wiring full policy runtime.
        from core.harness.kernel.execution_context import get_active_request_context

        if get_active_request_context() is None:
            pr = type("_PR", (), {"decision": PolicyDecision.ALLOW, "tenant_id": None, "reason": None})()
        else:
            pr = await policy_gate.check_tool(user_id=user_id, tool_name=tool_name or "<unknown>", tool_args=args)
    except Exception:
        pr = await policy_gate.check_tool(user_id=user_id, tool_name=tool_name or "<unknown>", tool_args=args)
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

    # PR-12: Tenant quotas (best-effort). Block before executing the tool.
    try:
        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        tenant_id = args.get("_tenant_id")
        if store is not None and tenant_id:
            quota_item = await store.get_tenant_quota(tenant_id=str(tenant_id))
            quota = quota_item.get("quota") if isinstance(quota_item, dict) else {}
            daily = quota.get("daily") if isinstance(quota, dict) and isinstance(quota.get("daily"), dict) else {}
            limit_calls = daily.get("tool_calls")
            if limit_calls is not None:
                try:
                    limit_i = int(limit_calls)
                except Exception:
                    limit_i = None
                if limit_i is not None:
                    day = time.strftime("%Y-%m-%d", time.gmtime())
                    cur = await store.get_tenant_usage(tenant_id=str(tenant_id), day=str(day), metric_key="tool_calls")
                    if cur >= float(limit_i):
                        reason = f"tenant quota exceeded: tool_calls {cur}/{limit_i} (day={day})"
                        try:
                            await store.add_syscall_event(
                                {
                                    "trace_id": span.trace_id,
                                    "span_id": getattr(span, "span_id", None),
                                    "run_id": (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                                    "kind": "tool",
                                    "name": tool_name or "<unknown>",
                                    "status": "quota_exceeded",
                                    "target_type": _ar.target_type if _ar else None,
                                    "target_id": _ar.target_id if _ar else None,
                                    "tenant_id": str(tenant_id),
                                    "user_id": user_id,
                                    "session_id": session_id,
                                    "start_time": start_ts,
                                    "end_time": start_ts,
                                    "duration_ms": 0.0,
                                    "args": {"tool_args": args},
                                    "error": reason,
                                    "error_code": "QUOTA_EXCEEDED",
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
                                    tenant_id=str(tenant_id),
                                    payload={"tool": tool_name or "<unknown>", "status": "quota_exceeded", "error": "QUOTA_EXCEEDED"},
                                )
                        except Exception:
                            pass
                        try:
                            await store.add_audit_log(
                                action="tool_quota_exceeded",
                                status="denied",
                                tenant_id=str(tenant_id),
                                actor_id=user_id,
                                resource_type="tool",
                                resource_id=tool_name or "<unknown>",
                                run_id=str(_run_id) if _run_id else None,
                                trace_id=span.trace_id,
                                detail={"reason": reason, "day": day, "limit": limit_i, "current": cur},
                            )
                        except Exception:
                            pass
                        await trace_gate.end(span, success=False)
                        return ToolResult(
                            success=False,
                            output=None,
                            error="quota_exceeded",
                            metadata={"reason": reason, "tenant_id": str(tenant_id), "tool": tool_name, "limit": limit_i, "current": cur},
                        )
                    # consume 1 call budget pre-execution (counts attempts)
                    try:
                        await store.add_tenant_usage(tenant_id=str(tenant_id), metric_key="tool_calls", amount=1.0, day=day)
                    except Exception:
                        pass
    except Exception:
        pass

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
                        # P2-1: avoid storing large SOP bodies in syscall events (keep summary only).
                        "result": {
                            "output": _sanitize_tool_output_for_syscall_event(
                                tool_name=tool_name or "<unknown>",
                                output=getattr(result, "output", None),
                            ),
                            "error": getattr(result, "error", None),
                        },
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


def _sanitize_tool_output_for_syscall_event(*, tool_name: str, output: Any) -> Any:
    """
    Reduce persistence footprint for tool syscall events.
    - skill_load: SOP markdown can be large; store only summary fields + a short excerpt.
    """
    try:
        if tool_name != "skill_load":
            return output
        if not isinstance(output, dict):
            return output
        out = dict(output)
        sop = out.get("sop_markdown")
        if isinstance(sop, str) and sop:
            out["sop_excerpt"] = sop[:160]
            out.pop("sop_markdown", None)
        return out
    except Exception:
        return output
