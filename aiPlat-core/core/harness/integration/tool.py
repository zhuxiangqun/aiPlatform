"""Auto-extracted from integration.py — 2026-07-13"""
from __future__ import annotations


async def _execute_tool_impl(self, req: ExecutionRequest) -> ExecutionResult:
    from core.harness.kernel.types import ExecutionResult
    registry = _resolve_tool_registry()
    tool = registry.get(req.target_id)
    if not tool:
        return self._fail(code="NOT_FOUND", message=f"Tool {req.target_id} not found", http_status=404)

    payload = req.payload or {}
    input_data = payload.get("input", {}) if isinstance(payload, dict) else {}

    runtime = getattr(self, "_runtime", None)

    # Phase R2: apply workspace context for toolset gating.
    workspace_token = None
    request_token = None
    tenant_policy_token = None
    requested_toolset = None
    token = None
    audit_token = None
    audit_data = None
    active_release = None
    tenant_id = None
    try:
        from core.harness.kernel.execution_context import (
            ActiveRequestContext,
            ActiveTenantPolicyContext,
            ActiveWorkspaceContext,
            set_active_request_context,
            set_active_tenant_policy_context,
            set_active_workspace_context,
        )

        repo_root = None
        if isinstance(payload, dict):
            opts = payload.get("options") if isinstance(payload.get("options"), dict) else {}
            ctx0 = payload.get("context") if isinstance(payload.get("context"), dict) else {}
            requested_toolset = (
                (opts.get("toolset") if isinstance(opts, dict) else None)
                or payload.get("toolset")
                or ctx0.get("toolset")
                or ctx0.get("_toolset")
            )
            inp0 = payload.get("input")
            if isinstance(inp0, dict):
                repo_root = inp0.get("directory") or inp0.get("repo_root") or inp0.get("workspace_root")
            if not repo_root and isinstance(ctx0, dict):
                repo_root = ctx0.get("directory") or ctx0.get("repo_root") or ctx0.get("workspace_root")
        if requested_toolset or (isinstance(repo_root, str) and repo_root.strip()):
            workspace_token = set_active_workspace_context(
                ActiveWorkspaceContext(
                    repo_root=repo_root.strip() if isinstance(repo_root, str) and repo_root.strip() else None,
                    toolset=str(requested_toolset) if requested_toolset else None,
                )
            )
        # Always set request context for downstream prompt assembly.
        try:
            ctx0 = payload.get("context") if isinstance(payload.get("context"), dict) else {}
            sess_id = payload.get("session_id") or ctx0.get("session_id") or req.session_id
            tenant_id = ctx0.get("tenant_id") if isinstance(ctx0, dict) else None
            request_token = set_active_request_context(
                ActiveRequestContext(
                    user_id=str(req.user_id or "system"),
                    session_id=str(sess_id or "default"),
                    tenant_id=str(ctx0.get("tenant_id")) if isinstance(ctx0, dict) and ctx0.get("tenant_id") else None,
                    actor_id=str(ctx0.get("actor_id")) if isinstance(ctx0, dict) and ctx0.get("actor_id") else str(req.user_id or "system"),
                    actor_role=str(ctx0.get("actor_role")) if isinstance(ctx0, dict) and ctx0.get("actor_role") else None,
                    entrypoint=str(ctx0.get("entrypoint") or ctx0.get("source")) if isinstance(ctx0, dict) and (ctx0.get("entrypoint") or ctx0.get("source")) else None,
                    request_id=str(ctx0.get("request_id")) if isinstance(ctx0, dict) and ctx0.get("request_id") else getattr(req, "request_id", None),
                )
            )
        except Exception:
            request_token = None

        # Tenant policy snapshot (best-effort)
        try:
            from core.services.tenant_store_protocol import get_tenant_store  # P0-A3

            store = get_tenant_store() or (getattr(runtime, "execution_store", None) if runtime else None)
            if tenant_id and store:
                rec = await store.get_tenant_policy(tenant_id=str(tenant_id))
                pol = rec.get("policy") if isinstance(rec, dict) and isinstance(rec.get("policy"), dict) else {}
                ver = rec.get("version") if isinstance(rec, dict) else None
                tenant_policy_token = set_active_tenant_policy_context(
                    ActiveTenantPolicyContext(tenant_id=str(tenant_id), version=int(ver) if isinstance(ver, int) else None, policy=pol)
                )
        except Exception:
            tenant_policy_token = None
    except Exception:
        workspace_token = None
        request_token = None
        tenant_policy_token = None

    # Phase 6.7: optional LearningApplier (behavior-preserving; metadata-only)
    if os.getenv("AIPLAT_ENABLE_LEARNING_APPLIER", "false").lower() in ("1", "true", "yes", "y"):
        try:
            from core.learning.apply import LearningApplier

            applier = LearningApplier(self._runtime.execution_store if self._runtime else None)
            active_release = await applier.resolve_active_release(target_type="tool", target_id=str(req.target_id))
        except Exception:
            active_release = None

    # Phase 6.8: set per-request active release context for syscalls (behavior change is gated elsewhere).
    if active_release is not None:
        try:
            from core.harness.kernel.execution_context import (
                ActiveReleaseContext,
                PromptRevisionAudit,
                set_active_release_context,
                set_prompt_revision_audit,
            )

            token = set_active_release_context(
                ActiveReleaseContext(
                    target_type="tool",
                    target_id=str(req.target_id),
                    candidate_id=active_release.candidate_id,
                    version=active_release.version,
                    summary=active_release.summary,
                )
            )
            audit_token = set_prompt_revision_audit(
                PromptRevisionAudit(applied_ids=[], ignored_ids=[], conflicts=[], llm_calls=0, updated_at=0.0)
            )
        except Exception:
            token = None
            audit_token = None

    # Add a trace for tool execute so syscall spans are linked (best-effort).
    trace_id = None
    # Keep tool executions under the same run_id namespace.
    run_id = str(getattr(req, "run_id", None) or "") or new_prefixed_id("run")
    if runtime and runtime.trace_service:
        try:
            attrs = {"tool_name": req.target_id, "run_id": run_id, "user_id": req.user_id or "system"}
            if getattr(req, "request_id", None):
                attrs["request_id"] = req.request_id
            try:
                ctx0 = (payload or {}).get("context") if isinstance(payload, dict) else None
                if isinstance(ctx0, dict) and ctx0:
                    if ctx0.get("source") == "job":
                        if ctx0.get("job_id"):
                            attrs["job_id"] = ctx0.get("job_id")
                        if ctx0.get("job_run_id"):
                            attrs["job_run_id"] = ctx0.get("job_run_id")
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            t = await runtime.trace_service.start_trace(name=f"tool:{req.target_id}", attributes=attrs)
            trace_id = t.trace_id
        except Exception:
            trace_id = None

    # Run events (best-effort): start
    if runtime and runtime.execution_store:
        try:
            exec_backend = None
            try:
                exec_backend = await _resolve_exec_backend()
            except Exception:
                exec_backend = None
            await runtime.execution_store.append_run_event(
                run_id=run_id,
                event_type="run_start",
                trace_id=trace_id,
                tenant_id=str(tenant_id) if tenant_id else None,
                payload={
                    "kind": "tool",
                    "tool_name": req.target_id,
                    "user_id": req.user_id or "system",
                    "session_id": req.session_id,
                    "exec_backend": exec_backend,
                    "active_release": active_release.to_dict() if active_release is not None else None,
                    "request_payload": self._redact_request_payload(req.payload if isinstance(req.payload, dict) else {}),
                },
            )
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    try:
        result = await sys_tool_call(
            tool,
            input_data if isinstance(input_data, dict) else {},
            user_id=req.user_id,
            session_id=req.session_id,
            timeout_seconds=60,
            trace_context={"trace_id": trace_id, "run_id": run_id, "tenant_id": tenant_id} if trace_id else {"run_id": run_id, "tenant_id": tenant_id},
        )
        # Snapshot prompt revision audit before emitting run_end.
        if audit_token is not None:
            try:
                from core.harness.kernel.execution_context import get_prompt_revision_audit

                audit = get_prompt_revision_audit()
                audit_data = audit.to_dict() if audit is not None else None
            except Exception:
                audit_data = None
        # Roadmap-4: persist session messages for cross-session search (best-effort).
        if runtime and runtime.execution_store:
            try:
                sess_id = str(req.session_id or "default")
                await runtime.execution_store.add_memory_message(
                    session_id=sess_id,
                    user_id=str(req.user_id or "system"),
                    role="user",
                    content=str(input_data),
                    metadata={"trace_id": trace_id, "run_id": run_id, "tool_name": req.target_id},
                    trace_id=trace_id,
                    run_id=run_id,
                )
                await runtime.execution_store.add_memory_message(
                    session_id=sess_id,
                    user_id=str(req.user_id or "system"),
                    role="assistant",
                    content=str(getattr(result, "output", str(result))),
                    metadata={"trace_id": trace_id, "run_id": run_id, "tool_name": req.target_id},
                    trace_id=trace_id,
                    run_id=run_id,
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        # Run events (best-effort): end
        if runtime and runtime.execution_store:
            try:
                await runtime.execution_store.append_run_event(
                    run_id=run_id,
                    event_type="run_end",
                    trace_id=trace_id,
                    tenant_id=str(tenant_id) if tenant_id else None,
                    payload={
                        "kind": "tool",
                        "tool_name": req.target_id,
                        "status": "completed" if getattr(result, "success", True) else "failed",
                        "error": getattr(result, "error", None),
                        "prompt_revision_audit": audit_data,
                    },
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        return ExecutionResult(
            ok=True,
            payload={
                "execution_id": run_id,
                "status": "completed" if getattr(result, "success", True) else "failed",
                "success": getattr(result, "success", True),
                "output": getattr(result, "output", str(result)),
                "error": self._normalize_error(
                    error=getattr(result, "error", None) or None,
                    metadata=getattr(result, "metadata", {}) or {},
                    fallback_message=str(getattr(result, "error", None) or "执行失败"),
                ),
                "error_message": getattr(result, "error", None) or None,
                "error_detail": self._normalize_error(
                    error=getattr(result, "error", None) or None,
                    metadata=getattr(result, "metadata", {}) or {},
                    fallback_message=str(getattr(result, "error", None) or "执行失败"),
                ),
                "latency": getattr(result, "latency", 0),
                "metadata": getattr(result, "metadata", {}) or {},
                "active_release": active_release.to_dict() if active_release is not None else None,
                "prompt_revision_audit": audit_data,
                "trace_id": trace_id,
                "run_id": run_id,
                "toolset": str(requested_toolset) if requested_toolset else None,
            },
            trace_id=trace_id,
            run_id=run_id,
            error_detail=self._normalize_error(
                error=getattr(result, "error", None) or None,
                metadata=getattr(result, "metadata", {}) or {},
                fallback_message=str(getattr(result, "error", None) or "执行失败"),
            ),
        )
    except asyncio.TimeoutError:
        if runtime and runtime.execution_store:
            try:
                await runtime.execution_store.append_run_event(
                    run_id=run_id,
                    event_type="run_end",
                    trace_id=trace_id,
                    tenant_id=str(tenant_id) if tenant_id else None,
                    payload={"kind": "tool", "tool_name": req.target_id, "status": "timeout", "error": "TIMEOUT"},
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        return self._fail(code="TIMEOUT", message="Tool execution timed out (60s)", http_status=504, trace_id=trace_id, run_id=run_id)
    except Exception as e:
        if runtime and runtime.execution_store:
            try:
                await runtime.execution_store.append_run_event(
                    run_id=run_id,
                    event_type="run_end",
                    trace_id=trace_id,
                    tenant_id=str(tenant_id) if tenant_id else None,
                    payload={"kind": "tool", "tool_name": req.target_id, "status": "failed", "error": str(e)},
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        return self._fail(code="EXCEPTION", message=str(e), http_status=500, trace_id=trace_id, run_id=run_id)
    finally:
        if runtime and runtime.trace_service and trace_id:
            try:
                from core.services.trace_service import SpanStatus

                await runtime.trace_service.end_trace(trace_id, status=SpanStatus.SUCCESS)
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        # Reset prompt revision audit
        if audit_token is not None:
            try:
                from core.harness.kernel.execution_context import reset_prompt_revision_audit

                reset_prompt_revision_audit(audit_token)
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        if token is not None:
            try:
                from core.harness.kernel.execution_context import reset_active_release_context

                reset_active_release_context(token)
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        if workspace_token is not None:
            try:
                from core.harness.kernel.execution_context import reset_active_workspace_context

                reset_active_workspace_context(workspace_token)
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        if request_token is not None:
            try:
                from core.harness.kernel.execution_context import reset_active_request_context

                reset_active_request_context(request_token)
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        if tenant_policy_token is not None:
            try:
                from core.harness.kernel.execution_context import reset_active_tenant_policy_context

                reset_active_tenant_policy_context(tenant_policy_token)
            except Exception as e:
                logging.debug(str(e), exc_info=True)
