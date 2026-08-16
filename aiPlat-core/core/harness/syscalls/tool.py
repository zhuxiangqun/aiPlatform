"""
sys_tool - Tool syscall wrappers (Phase 2).

Centralizes tool invocation so future gates can be enforced here:
- PolicyGate (permission + approval)
- TraceGate (span + audit record)
- ResilienceGate (timeout/retry)
"""

from __future__ import annotations

import asyncio
import logging
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
    from ._trace import trace_syscall_entry
    trace_syscall_entry("sys_tool_call")
    """
    Execute a tool call.

    Notes:
    - Injects `_user_id` / `_session_id` into args for downstream wrappers.

    边界:
      - 是否修改系统状态取决于具体工具——不能假设无副作用
      - tool_args 无 schema 校验时靠工具自身处理非法参数
      - 被 PolicyGate 拒绝时返回 ToolResult 而非抛异常——调用者必须检查 success 字段
    退路:
      - 权限不足 → 返回 approval_required，非自动重试
      - 工具不存在 → 返回 ToolResult(error="tool_not_found")
      - 需要只读操作 → 检查工具的 get_risk_level() 或 metadata.risk_level
    """
    policy_gate = PolicyGate()
    trace_gate = TraceGate()
    ctx_gate = ContextGate()
    res_gate = ResilienceGate()

    # Start span early so "fast-fail" (missing tool) is still observable.
    tool_name = str(getattr(tool, "name", None) or getattr(tool, "get_name", lambda: "")() or "")

    # PR #3: 工具白名单过滤 — 从 ControlProfile 读取 tool_whitelist
    try:
        from core.harness.meta.profile_registry import get_active_profile
        profile = get_active_profile()
        whitelist = profile.tool_whitelist
        if whitelist is not None and tool_name not in whitelist:
            logging.getLogger("aiplat.tool").warning(
                "Tool '%s' blocked by ControlProfile.tool_whitelist", tool_name)
            return ToolResult(
                success=False,
                error=f"tool_blocked_by_profile: '{tool_name}' not in whitelist",
            )
        # C: toolset scope restriction (readonly / voice_only)
        toolset = profile.toolset
        high_risk_tools = {"code_execution", "terminal", "file_write", "file_edit", "browser", "deploy"}
        if toolset == "readonly" and tool_name in high_risk_tools:
            return ToolResult(success=False,
                error=f"tool_blocked_by_readonly: '{tool_name}' requires full access")
        if toolset == "voice_only" and tool_name not in {"sys_knowledge_retrieve", "sys_wiki_context", "sys_tts_generate"}:
            return ToolResult(success=False,
                error=f"tool_blocked_by_voice_only: '{tool_name}' not allowed in voice-only mode")
    except Exception:
        logging.getLogger(__name__).debug('sys_tool_call failed', exc_info=True)

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
    except Exception as e:
        logging.warning(str(e), exc_info=True)

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
                        "parent_span_id": (trace_context or {}).get("parent_span_id") if isinstance(trace_context, dict) else None,
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
            except Exception as e:
                logging.warning(str(e), exc_info=True)
            try:
                if _run_id:
                    await store.append_run_event(
                        run_id=str(_run_id),
                        event_type="tool_end",
                        trace_id=span.trace_id,
                        tenant_id=(trace_context or {}).get("tenant_id") if isinstance(trace_context, dict) else None,
                        payload={"tool": tool_name or "<unknown>", "status": "failed", "error": "TOOL_NOT_EXECUTABLE"},
                    )
            except Exception as e:
                logging.warning(str(e), exc_info=True)
        raise RuntimeError("Tool is not executable")

    args = dict(tool_args or {})
    # Tenant propagation for policy-as-code (best-effort).
    try:
        if isinstance(trace_context, dict) and trace_context.get("tenant_id") and "_tenant_id" not in args:
            args["_tenant_id"] = trace_context.get("tenant_id")
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    # Fallback tenant propagation from active request context.
    try:
        if "_tenant_id" not in args:
            from core.harness.kernel.execution_context import get_active_request_context

            arq = get_active_request_context()
            if arq and getattr(arq, "tenant_id", None):
                args["_tenant_id"] = getattr(arq, "tenant_id")
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    # PR-08: persist run_id for approval replay/links (best-effort).
    try:
        _run_id = (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None
        if _run_id and "_run_id" not in args:
            args["_run_id"] = str(_run_id)
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    # Fallback run_id: for nested calls, session_id is often the run_id.
    try:
        if "_run_id" not in args and isinstance(session_id, str) and session_id.startswith(("run_", "run-")):
            args["_run_id"] = str(session_id)
    except Exception as e:
        logging.warning(str(e), exc_info=True)
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
    except Exception as e:
        logging.warning(str(e), exc_info=True)
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
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # P4: approval layering policy (skill-only / sensitive-only)
    # If a parent skill has already been approved, we can reuse the same approval_request_id
    # for nested tool calls to avoid double-approval when configured.
    try:
        approval_layer_policy = str(os.getenv("AIPLAT_APPROVAL_LAYER_POLICY", "both") or "both").strip().lower()
        if os.getenv("AIPLAT_APPROVALS_DISABLED", "").lower() in ("1", "true", "yes"):
            approval_layer_policy = "none"
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
        except Exception as e:
            logging.warning(str(e), exc_info=True)
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
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # P1-1: Exec backend gate (force approval for non-local execution backends).
    # Tool categories are defined per-tool via config, not hardcoded here.
    # The tool_name comparison against well-known tool categories ("code", "repo")
    # is transitional — future: check tool.needs_exec_backend / tool.mutates_repo attributes.
    execution_tools = set(os.getenv("AIPLAT_EXECUTION_TOOLS", "code").split(","))
    try:
        if tool_name in execution_tools:
            # DI: get_exec_backend via ExecBackend resolver

            try:
                from core.harness.integration import _resolve_exec_backend
                backend = await _resolve_exec_backend()
            except Exception:
                try:
                    from core.harness.integration import get_exec_backend
                    backend = await get_exec_backend()
                except Exception:
                    backend = None
            args.setdefault("_exec_backend", backend)
            if str(backend) and str(backend) != "local":
                args["_approval_required"] = True
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # P0: repo-aware workflow gate (force approval for mutating git operations).
    repo_tools = set(os.getenv("AIPLAT_REPO_TOOLS", "repo").split(","))
    try:
        if tool_name in repo_tools:
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
                except Exception as e:
                    logging.warning(str(e), exc_info=True)

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
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # Phase R2: Toolset gate (runtime allowlist). Fail-closed when a toolset is active.
    # Uses shared check_workspace_gate() for consistency with skill/agent syscalls.
    try:
        from core.harness.tools.toolsets import check_workspace_gate

        allowed, reason, active_toolset = check_workspace_gate(
            "tool", tool_name or "<unknown>", args
        )
        if not allowed:
            try:
                runtime = get_kernel_runtime()
                store = getattr(runtime, "execution_store", None) if runtime else None
                if store is not None:
                    await store.add_syscall_event(
                        {
                            "trace_id": span.trace_id,
                            "span_id": getattr(span, "span_id", None),
                            "parent_span_id": (trace_context or {}).get("parent_span_id") if isinstance(trace_context, dict) else None,
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
                            "args": {"tool_args": args, "toolset": active_toolset},
                            "error": reason or "toolset_denied",
                            "error_code": "TOOLSET_DENIED",
                        }
                    )
            except Exception as e:
                logging.warning(str(e), exc_info=True)
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
            except Exception as e:
                logging.warning(str(e), exc_info=True)
            return ToolResult(
                success=False,
                output=None,
                error="toolset_denied",
                metadata={"reason": reason, "tool": tool_name, "toolset": active_toolset},
            )
    except Exception:
        # Best-effort: do not break existing behavior if toolset gate fails.
        import logging as _logging
        _logging.getLogger("aiplat.syscall.tool").debug("Toolset gate check skipped", exc_info=True)

    # SandboxGate — pre-execution safety validation (filesystem, rate limit, patterns)
    try:
        from core.harness.infrastructure.gates.sandbox_gate import get_sandbox, Verdict
        sb = get_sandbox()
        sb_result = await sb.check(
            kind="tool", tool_name=tool_name or "", tool_args=args,
            file_path=args.get("path", "") or args.get("file_path", "") or args.get("target", ""),
        )
        if sb_result.verdict == Verdict.REJECT:
            return ToolResult(ok=False, error=f"Sandbox rejected: {sb_result.reason}",
                            error_code="SANDBOX_REJECT", output={"sandbox_details": sb_result.details})
        elif sb_result.verdict == Verdict.WARN:
            logging.getLogger("aiplat.sandbox").warning("Sandbox warning for %s: %s", tool_name, sb_result.reason)
    except Exception:
        logging.getLogger("aiplat.sandbox").debug("SandboxGate skipped", exc_info=True)

    # PolicyGate (permission; approval optional via env flag)
    try:
        # Mark gate coverage (Phase 3 GateTracer)
        from core.harness.kernel.execution_context import mark_gate_passed
        mark_gate_passed("policy_gate_tool")
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    try:
        # No active request context (internal/background/test calls): the trusted "system"
        # default stays fail-open so pure harness tests can run dummy tools without wiring
        # a full request context. Any EXPLICIT non-system identity is still enforced via
        # PolicyGate even without context — closes the cross-actor bypass (background jobs /
        # sub-agents that pass a real user_id but forget to propagate request context).
        from core.harness.kernel.execution_context import get_active_request_context

        if get_active_request_context() is None and str(user_id) == "system":
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
                        "parent_span_id": (trace_context or {}).get("parent_span_id") if isinstance(trace_context, dict) else None,
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
            except Exception as e:
                logging.warning(str(e), exc_info=True)
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
            except Exception as e:
                logging.warning(str(e), exc_info=True)
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
        except Exception as e:
            logging.warning(str(e), exc_info=True)
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
                        "parent_span_id": (trace_context or {}).get("parent_span_id") if isinstance(trace_context, dict) else None,
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
            except Exception as e:
                logging.warning(str(e), exc_info=True)
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
            except Exception as e:
                logging.warning(str(e), exc_info=True)
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
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
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
        except Exception as e:
            logging.warning(str(e), exc_info=True)
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

    # Phase 41: Decision Lineage — capture tool selection decision (best-effort)
    _decision_id: Optional[str] = None
    try:
        from core.harness.infrastructure.decision_capture import capture_tool_decision
        _decision_id = await capture_tool_decision(
            tool_name, prepared_args, trace_context,
            reason="",
        )
    except Exception:
        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

    # Phase 11: LLM parameter completion — fill in missing/inferred params
    try:
        prepared_args = await _llm_complete_params(tool, prepared_args, tool_name or "")
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    async def _run():
        return await tool.execute(prepared_args)  # type: ignore[misc]

    try:
        # Set ActiveTraceContext for downstream event emission
        from core.harness.kernel.execution_context import ActiveTraceContext, set_active_trace_context, reset_active_trace_context
        run_id_val = str((trace_context or {}).get("run_id") or "") if isinstance(trace_context, dict) else ""
        span_id_val = getattr(span, "span_id", "")
        trace_token = set_active_trace_context(ActiveTraceContext(
            run_id=run_id_val,
            span_id=str(span_id_val),
            parent_span_id=str((trace_context or {}).get("parent_span_id") or "") if isinstance(trace_context, dict) else "",
        )) if run_id_val else None
        try:
            retries = int(os.getenv("AIPLAT_TOOL_RETRIES", "0") or "0")
            result = await res_gate.run(_run, retries=retries, timeout_seconds=timeout_seconds)
        finally:
            if trace_token is not None:
                try:
                    reset_active_trace_context(trace_token)
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
        # P0-2: enrich failed results with structured error diagnostics for Agent self-healing
        result = _enrich_tool_error(result)
        end_ts = time.time()

        # Phase 41: Update decision outcome (best-effort)
        if _decision_id:
            try:
                from core.harness.infrastructure.decision_capture import update_decision_outcome
                success = bool(getattr(result, "success", True))
                await update_decision_outcome(
                    _decision_id,
                    outcome_status="success" if success else "failed",
                    outcome_summary=str(getattr(result, "output", ""))[:200] if success else str(getattr(result, "error", ""))[:200],
                )
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

        # Phase 44: Operation Recording (best-effort, zero-cost when not recording)
        try:
            from core.harness.learning.operation_recorder import OperationRecorder
            recorder = OperationRecorder.get()
            if recorder.is_recording():
                recorder.record_step(
                    tool_name=tool_name or '<unknown>',
                    tool_args=prepared_args if 'prepared_args' in dir() else {},
                    result_type='success' if bool(getattr(result, 'success', True)) else 'failed',
                    result_summary=str(getattr(result, 'output', ''))[:200] if bool(getattr(result, 'success', True)) else str(getattr(result, 'error', ''))[:200],
                    duration_ms=(end_ts - start_ts) * 1000,
                )
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

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
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
                await store.add_syscall_event(
                    {
                        "trace_id": span.trace_id,
                        "span_id": getattr(span, "span_id", None),
                        "parent_span_id": (trace_context or {}).get("parent_span_id") if isinstance(trace_context, dict) else None,
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
            except Exception as e:
                logging.warning(str(e), exc_info=True)
        # ToolDriftDetector: record this call for drift analysis (non-blocking)
        try:
            from core.harness.learning.tool_drift_detector import get_drift_detector
            dd = get_drift_detector()
            dd.record_call(
                tool_name=tool_name or "<unknown>",
                request_schema=prepared_args if isinstance(prepared_args, dict) else {},
                response_data={"output": _sanitize_tool_output_for_syscall_event(tool_name or "<unknown>", getattr(result, "output", None))} if hasattr(result, "output") else {},
                status_code=200 if bool(getattr(result, "success", True)) else 500,
                latency_ms=(end_ts - start_ts) * 1000.0,
                error_code=getattr(result, "error", None),
            )
        except Exception:
            logging.getLogger(__name__).debug('code failed', exc_info=True)
        # ToolEvolutionEngine: record call for auto-improvement/deprecation (C4)
        try:
            from core.harness.optimization.tool_evolution import get_tool_evolution
            te = get_tool_evolution()
            te.record_call(
                tool_name=tool_name or "<unknown>",
                success=bool(getattr(result, "success", True)),
                latency_ms=(end_ts - start_ts) * 1000.0,
                error_type=getattr(result, "error_type", "") or "",
                error_message=str(getattr(result, "error", "") or "")[:500],
            )
        except Exception:
            logging.getLogger(__name__).debug('code failed', exc_info=True)
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
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
                await store.add_syscall_event(
                    {
                        "trace_id": span.trace_id,
                        "span_id": getattr(span, "span_id", None),
                        "parent_span_id": (trace_context or {}).get("parent_span_id") if isinstance(trace_context, dict) else None,
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
            except Exception as e:
                logging.warning(str(e), exc_info=True)
        raise


def _enrich_tool_error(result: Any) -> Any:
    """Populate structured error diagnostics on a failed ToolResult.

    Gives the Agent machine-readable self-healing signals (error_type / recovery_hint /
    exit_code / stderr) via the shared ErrorTranslator classification, instead of an
    opaque ``error`` string (Hermes Layer 2 self-healing loop). No-op for successes or
    results that already carry a classification. Never raises.
    """
    try:
        if result is None or getattr(result, "success", True):
            return result
        if getattr(result, "error_type", None):
            return result
        from core.harness.infrastructure.gates.error_translator import (
            classify_api_error, recovery_hint_for,
        )
        err_msg = str(getattr(result, "error", "") or "")
        out = getattr(result, "output", None)
        exit_code = None
        stderr = None
        if isinstance(out, dict):
            exit_code = out.get("exit_code", out.get("returncode"))
            stderr = out.get("stderr")
        # Route the tool error string to the exception TYPE the LLM-tuned classifier
        # understands (timeout/connection are matched by type, not message text).
        _low = (err_msg or str(stderr or "")).lower()
        if any(k in _low for k in ("timed out", "timeout")):
            probe: Exception = TimeoutError(err_msg or "timeout")
        elif any(k in _low for k in ("connection refused", "connection reset",
                                     "connection aborted", "connection error")):
            probe = ConnectionError(err_msg or "connection error")
        else:
            probe = RuntimeError(err_msg or (str(stderr or "")))
        classified = classify_api_error(probe)
        try:
            result.error_type = classified.reason.value
            result.recovery_hint = recovery_hint_for(classified.reason)
            if getattr(result, "exit_code", None) is None and exit_code is not None:
                result.exit_code = int(exit_code)
            if getattr(result, "stderr", None) is None and stderr:
                result.stderr = str(stderr)[:2000]
        except Exception:
            logging.getLogger(__name__).debug('_enrich_tool_error failed', exc_info=True)
    except Exception:
        return result
    return result


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


async def _llm_complete_params(tool: Any, args: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
    u"""LLM parameter completion: fill inferred/context-dependent params.

    If the tool has a __tool_contract__ with param_draft, use LLM to
    complete parameter values based on the current context.

    Args:
        tool: the tool object (may have __tool_contract__).
        args: the current parameter dict.
        tool_name: tool identifier for logging.

    Returns:
        Completed args dict (or original if no draft).
    """
    contract = getattr(tool, "__tool_contract__", None)
    if not isinstance(contract, dict):
        return args

    param_draft = contract.get("param_draft", {})
    if not param_draft:
        return args

    # Only complete if args have placeholder values (None, empty str, or "auto")
    needs_completion = any(
        args.get(k) in (None, "", "auto")
        for k in param_draft
    )
    if not needs_completion:
        return args

    try:
        from core.harness.syscalls.llm import sys_llm_generate
        from core.harness.utils.model_injection import best_model_for_purpose

        prompt = (
            f"Complete the parameters for tool call '{tool_name}'.\n\n"
            f"Parameter hints:\n"
            + "\n".join(f"  {k}: {v}" for k, v in param_draft.items())
            + f"\n\nCurrent args: {args}\n"
            f"Fill in missing/inferred values. Return JSON only:\n"
            f"{str(args)} with missing fields completed."
        )

        resp = await sys_llm_generate(
            None, [{"role": "user", "content": prompt}],
            model_name=best_model_for_purpose("chat"),
            max_tokens=300,
        )
        content = getattr(resp, "content", "") or str(resp)
        import json as _json
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            completed = _json.loads(content[start:end + 1])
            if isinstance(completed, dict):
                # Merge: keep original explicit args, fill in completed ones
                merged = dict(args)
                for k, v in completed.items():
                    if args.get(k) in (None, "", "auto"):
                        merged[k] = v
                return merged
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    return args
