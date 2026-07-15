"""Auto-extracted from integration.py — 2026-07-13"""
from __future__ import annotations


async def _execute_skill_impl(self, req: ExecutionRequest) -> ExecutionResult:
    from core.apps.tools.permission import Permission  # noqa: data type (enum) — allowed
    from core.harness.kernel.types import ExecutionResult

    runtime = self._runtime
    perm = _resolve_or_import("PermissionManager", "core.apps.tools.permission:get_permission_manager")
    perm_mgr = perm() if callable(perm) else perm
    if runtime is None or runtime.skill_manager is None:
        return self._fail(code="NOT_INITIALIZED", message="Kernel runtime not initialized", http_status=503)

    skill_id = req.target_id
    user_id = req.user_id or (req.payload.get("context", {}) or {}).get("user_id", "system")

    if not perm_mgr.check_permission(user_id, skill_id, Permission.EXECUTE):
        return self._fail(
            code="PERMISSION_DENIED",
            message=f"User '{user_id}' lacks EXECUTE permission for skill '{skill_id}'",
            http_status=403,
        )

    trace_id = None
    if runtime.trace_service:
        try:
            attrs = {"skill_id": skill_id, "user_id": user_id}
            if getattr(req, "request_id", None):
                attrs["request_id"] = req.request_id
            try:
                ctx0 = (req.payload or {}).get("context") if isinstance(req.payload, dict) else None
                if isinstance(ctx0, dict) and ctx0:
                    if ctx0.get("source") == "job":
                        if ctx0.get("job_id"):
                            attrs["job_id"] = ctx0.get("job_id")
                        if ctx0.get("job_run_id"):
                            attrs["job_run_id"] = ctx0.get("job_run_id")
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            trace = await runtime.trace_service.start_trace(
                name=f"skill:{skill_id}",
                attributes=attrs,
            )
            trace_id = trace.trace_id
        except Exception:
            trace_id = None

    payload = req.payload or {}
    # Phase R2: apply workspace context for downstream syscalls (toolset gating).
    workspace_token = None
    request_token = None
    tenant_policy_token = None
    token = None
    audit_token = None
    audit_data = None
    active_release = None
    try:
        from core.harness.kernel.execution_context import (
            ActiveRequestContext,
            ActiveTenantPolicyContext,
            ActiveWorkspaceContext,
            set_active_request_context,
            set_active_tenant_policy_context,
            set_active_workspace_context,
        )

        requested_toolset = None
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
            request_token = set_active_request_context(
                ActiveRequestContext(
                    user_id=str(user_id or "system"),
                    session_id=str(sess_id or "default"),
                    tenant_id=str(ctx0.get("tenant_id")) if isinstance(ctx0, dict) and ctx0.get("tenant_id") else None,
                    actor_id=str(ctx0.get("actor_id")) if isinstance(ctx0, dict) and ctx0.get("actor_id") else str(user_id or "system"),
                    actor_role=str(ctx0.get("actor_role")) if isinstance(ctx0, dict) and ctx0.get("actor_role") else None,
                    entrypoint=str(ctx0.get("entrypoint") or ctx0.get("source")) if isinstance(ctx0, dict) and (ctx0.get("entrypoint") or ctx0.get("source")) else None,
                    request_id=getattr(req, "request_id", None),
                )
            )
        except Exception:
            request_token = None

        # Tenant policy snapshot (best-effort)
        try:
            store = getattr(runtime, "execution_store", None) if runtime else None
            tenant_id0 = ctx0.get("tenant_id") if isinstance(ctx0, dict) else None
            if tenant_id0 and store:
                rec = await store.get_tenant_policy(tenant_id=str(tenant_id0))
                pol = rec.get("policy") if isinstance(rec, dict) and isinstance(rec.get("policy"), dict) else {}
                ver = rec.get("version") if isinstance(rec, dict) else None
                tenant_policy_token = set_active_tenant_policy_context(
                    ActiveTenantPolicyContext(tenant_id=str(tenant_id0), version=int(ver) if isinstance(ver, int) else None, policy=pol)
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
            active_release = await applier.resolve_active_release(target_type="skill", target_id=str(skill_id))
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
                    target_type="skill",
                    target_id=str(skill_id),
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

    try:
        execution = await runtime.skill_manager.execute_skill(
            skill_id,
            payload.get("input"),
            context=payload.get("context") or {},
            mode=payload.get("mode", "inline"),
            execution_id=req.run_id,
        )
    except Exception as e:
        return self._fail(code="EXCEPTION", message=str(e), http_status=500, trace_id=trace_id)
    finally:
        # Capture then reset prompt revision audit
        if audit_token is not None:
            try:
                from core.harness.kernel.execution_context import get_prompt_revision_audit, reset_prompt_revision_audit

                audit = get_prompt_revision_audit()
                audit_data = audit.to_dict() if audit is not None else None
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

    # Persist execution (best effort)
    if runtime.execution_store:
        try:
            tenant_id = None
            try:
                ctx0 = payload.get("context") if isinstance(payload.get("context"), dict) else {}
                tenant_id = ctx0.get("tenant_id") if isinstance(ctx0, dict) else None
            except Exception:
                tenant_id = None
            meta2 = {
                "mode": payload.get("mode", "inline"),
                "session_id": (payload.get("context") or {}).get("session_id", req.session_id),
            }
            if active_release is not None:
                try:
                    meta2.setdefault("active_release", active_release.to_dict())
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
            if audit_data is not None:
                meta2.setdefault("prompt_revision_audit", audit_data)
            if tenant_id:
                meta2["tenant_id"] = str(tenant_id)
            try:
                meta2.setdefault(
                    "error_detail",
                    self._normalize_error(
                        error=execution.error,
                        metadata={
                            "skill_id": execution.skill_id,
                            "status": execution.status,
                            **(execution.metadata if isinstance(getattr(execution, "metadata", None), dict) else {}),
                        },
                        fallback_message=str(execution.error or "执行失败"),
                    ),
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            try:
                exec_backend = None
                try:
                    exec_backend = await _resolve_exec_backend()
                except Exception:
                    exec_backend = None
                await runtime.execution_store.append_run_event(
                    run_id=execution.id,
                    event_type="run_start",
                    trace_id=trace_id,
                    tenant_id=str(tenant_id) if tenant_id else None,
                    payload={
                        "kind": "skill",
                        "skill_id": execution.skill_id,
                        "user_id": user_id,
                        "session_id": meta2.get("session_id"),
                        "exec_backend": exec_backend,
                        "active_release": active_release.to_dict() if active_release is not None else None,
                        "request_payload": self._redact_request_payload(req.payload if isinstance(req.payload, dict) else {}),
                    },
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            await runtime.execution_store.upsert_skill_execution(
                {
                    "id": execution.id,
                    "skill_id": execution.skill_id,
                    "tenant_id": str(tenant_id) if tenant_id else None,
                    "status": execution.status,
                    "input": execution.input_data,
                    "output": execution.output_data,
                    "error": execution.error,
                    "start_time": execution.start_time.timestamp() if execution.start_time else 0.0,
                    "end_time": execution.end_time.timestamp() if execution.end_time else 0.0,
                    "duration_ms": execution.duration_ms or 0,
                    "user_id": user_id,
                    "trace_id": trace_id,
                    "metadata": {**meta2, **(execution.metadata if isinstance(getattr(execution, "metadata", None), dict) else {})},
                }
            )
            # Roadmap-4: persist session messages for cross-session search (best-effort).
            try:
                sess_id = str(meta2.get("session_id") or req.session_id or "default")
                if execution.input_data is not None:
                    await runtime.execution_store.add_memory_message(
                        session_id=sess_id,
                        user_id=str(user_id or "system"),
                        role="user",
                        content=str(execution.input_data),
                        metadata={"trace_id": trace_id, "run_id": execution.id, "skill_id": execution.skill_id},
                        trace_id=trace_id,
                        run_id=execution.id,
                    )
                if execution.output_data is not None:
                    await runtime.execution_store.add_memory_message(
                        session_id=sess_id,
                        user_id=str(user_id or "system"),
                        role="assistant",
                        content=str(execution.output_data),
                        metadata={"trace_id": trace_id, "run_id": execution.id, "skill_id": execution.skill_id},
                        trace_id=trace_id,
                        run_id=execution.id,
                    )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            try:
                await runtime.execution_store.append_run_event(
                    run_id=execution.id,
                    event_type="run_end",
                    trace_id=trace_id,
                    tenant_id=str(tenant_id) if tenant_id else None,
                    payload={
                        "kind": "skill",
                        "skill_id": execution.skill_id,
                        "status": execution.status,
                        "error": execution.error,
                        "prompt_revision_audit": audit_data,
                    },
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    if runtime.trace_service and trace_id:
        try:
            from core.services.trace_service import SpanStatus

            await runtime.trace_service.end_trace(
                trace_id, status=SpanStatus.SUCCESS if execution.status == "completed" else SpanStatus.FAILED
            )
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    return ExecutionResult(
        ok=True,
        payload={
            "execution_id": execution.id,
            "skill_id": execution.skill_id,
            "status": execution.status,
            "input": execution.input_data,
            "output": execution.output_data,
            "metadata": execution.metadata if isinstance(getattr(execution, "metadata", None), dict) else {},
            "error": self._normalize_error(
                error=execution.error,
                metadata={
                    "skill_id": execution.skill_id,
                    "status": execution.status,
                    **(execution.metadata if isinstance(getattr(execution, "metadata", None), dict) else {}),
                },
                fallback_message=str(execution.error or "执行失败"),
            ),
            "error_message": execution.error,
            "error_detail": self._normalize_error(
                error=execution.error,
                metadata={
                    "skill_id": execution.skill_id,
                    "status": execution.status,
                    **(execution.metadata if isinstance(getattr(execution, "metadata", None), dict) else {}),
                },
                fallback_message=str(execution.error or "执行失败"),
            ),
            "trace_id": trace_id,
            "run_id": execution.id,
            "start_time": execution.start_time.isoformat() if execution.start_time else None,
            "end_time": execution.end_time.isoformat() if execution.end_time else None,
            "duration_ms": execution.duration_ms,
        },
        trace_id=trace_id,
        run_id=execution.id,
        error_detail=self._normalize_error(
            error=execution.error,
            metadata={
                "skill_id": execution.skill_id,
                "status": execution.status,
                **(execution.metadata if isinstance(getattr(execution, "metadata", None), dict) else {}),
            },
            fallback_message=str(execution.error or "执行失败"),
        ),
    )
