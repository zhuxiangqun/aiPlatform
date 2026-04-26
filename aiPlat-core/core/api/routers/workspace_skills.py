from __future__ import annotations

import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Annotated, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from core.api.deps.rbac import actor_from_http, rbac_guard
from core.api.utils.governance import gate_error_envelope, governance_links, ui_url
from core.api.utils.run_contract import wrap_execution_result_as_run_summary
from core.apps.skills.registry import get_skill_registry
from core.harness.integration import get_harness, KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.kernel.types import ExecutionRequest
from core.schemas import RunStatus, SkillCreateRequest, SkillExecuteRequest
from core.utils.ids import new_prefixed_id

router = APIRouter()

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]


def _store(rt: Optional[KernelRuntime]):
    return getattr(rt, "execution_store", None) if rt else None


def _ws_skill_mgr(rt: Optional[KernelRuntime]):
    return getattr(rt, "workspace_skill_manager", None) if rt else None


def _ws_agent_mgr(rt: Optional[KernelRuntime]):
    return getattr(rt, "workspace_agent_manager", None) if rt else None


def _skill_mgr(rt: Optional[KernelRuntime]):
    return getattr(rt, "skill_manager", None) if rt else None


def _ws_mcp_mgr(rt: Optional[KernelRuntime]):
    return getattr(rt, "workspace_mcp_manager", None) if rt else None


def _mcp_mgr(rt: Optional[KernelRuntime]):
    return getattr(rt, "mcp_manager", None) if rt else None


def _job_scheduler(rt: Optional[KernelRuntime]):
    return getattr(rt, "job_scheduler", None) if rt else None


def _approval_mgr(rt: Optional[KernelRuntime]):
    return getattr(rt, "approval_manager", None) if rt else None


async def _audit_event(
    rt: Optional[KernelRuntime],
    kind: str,
    name: str,
    status: str,
    *,
    args: Dict[str, Any] | None = None,
    result: Dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """Best-effort append to ExecutionStore syscall_events for auditability."""
    try:
        store = _store(rt)
        if not store:
            return
        await store.add_syscall_event({"kind": kind, "name": name, "status": status, "args": args or {}, "result": result or {}, "error": error})
    except Exception:
        return


async def _record_changeset(
    rt: Optional[KernelRuntime],
    *,
    name: str,
    target_type: str,
    target_id: str,
    status: str = "success",
    args: Dict[str, Any] | None = None,
    result: Dict[str, Any] | None = None,
    error: str | None = None,
    trace_id: str | None = None,
    run_id: str | None = None,
    user_id: str = "admin",
    session_id: str | None = None,
    approval_request_id: str | None = None,
    tenant_id: str | None = None,
) -> None:
    from core.governance.changeset import record_changeset

    return await record_changeset(
        store=_store(rt),
        name=name,
        target_type=target_type,
        target_id=target_id,
        status=status,
        args=args,
        result=result,
        error=error,
        trace_id=trace_id,
        run_id=run_id,
        user_id=user_id,
        session_id=session_id,
        approval_request_id=approval_request_id,
        tenant_id=tenant_id,
    )


def _new_change_id() -> str:
    return f"chg-{uuid.uuid4().hex[:12]}"


def _inject_http_request_context(payload: Any, http_request: Request, *, entrypoint: str) -> Any:
    """
    Best-effort: inject tenant/actor/request identity from headers into payload.context.
    Used for PR-01 tenant/actor propagation into harness/syscalls.
    """
    if not isinstance(payload, dict):
        return payload
    try:
        ctx = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        ctx = dict(ctx) if isinstance(ctx, dict) else {}
        ctx.setdefault("entrypoint", str(entrypoint or "api"))

        tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID") or http_request.headers.get("x-aiplat-tenant-id")
        actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID") or http_request.headers.get("x-aiplat-actor-id")
        actor_role = http_request.headers.get("X-AIPLAT-ACTOR-ROLE") or http_request.headers.get("x-aiplat-actor-role")
        req_id = http_request.headers.get("X-AIPLAT-REQUEST-ID") or http_request.headers.get("x-aiplat-request-id")
        if tenant_id:
            ctx.setdefault("tenant_id", str(tenant_id))
        if actor_id:
            ctx.setdefault("actor_id", str(actor_id))
        if actor_role:
            ctx.setdefault("actor_role", str(actor_role))
        if req_id:
            ctx.setdefault("request_id", str(req_id))
        payload["context"] = ctx
    except Exception:
        return payload
    return payload


async def _audit_execute(
    rt: Optional[KernelRuntime],
    *,
    http_request: Request,
    payload: Optional[Dict[str, Any]],
    resource_type: str,
    resource_id: str,
    resp: Dict[str, Any],
    action: Optional[str] = None,
) -> None:
    """PR-06: enterprise audit for execute entrypoints (best-effort)."""
    store = _store(rt)
    if not store:
        return
    try:
        actor = actor_from_http(http_request, payload)
        await store.add_audit_log(
            action=action or f"execute_{resource_type}",
            status=str(resp.get("legacy_status") or resp.get("status") or ("ok" if resp.get("ok") else "failed")),
            tenant_id=str(actor.get("tenant_id") or "") or None,
            actor_id=str(actor.get("actor_id") or "") or None,
            actor_role=str(actor.get("actor_role") or "") or None,
            resource_type=str(resource_type),
            resource_id=str(resource_id),
            request_id=str(resp.get("request_id") or "") or (http_request.headers.get("X-AIPLAT-REQUEST-ID") or http_request.headers.get("x-aiplat-request-id")),
            run_id=str(resp.get("run_id") or resp.get("execution_id") or "") or None,
            trace_id=str(resp.get("trace_id") or "") or None,
            detail={"status": resp.get("status"), "legacy_status": resp.get("legacy_status"), "error": resp.get("error")},
        )
    except Exception:
        return


def _governance_publish_gate(meta: Dict[str, Any] | None) -> Dict[str, Any]:
    """
    If a workspace skill has a governance candidate, it must be published before enable/execute.
    """
    if not isinstance(meta, dict):
        return {"required": False}
    gov = meta.get("governance")
    if not isinstance(gov, dict):
        return {"required": False}
    candidate_id = gov.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        return {"required": False}
    candidate_id = candidate_id.strip()
    published_candidate_id = gov.get("published_candidate_id")
    if isinstance(published_candidate_id, str) and published_candidate_id.strip() == candidate_id:
        return {"required": False, "candidate_id": candidate_id, "published_candidate_id": published_candidate_id}
    if str(gov.get("status") or "").lower() == "published":
        return {"required": False, "candidate_id": candidate_id, "published_candidate_id": published_candidate_id}
    return {"required": True, "candidate_id": candidate_id, "published_candidate_id": published_candidate_id, "status": gov.get("status")}


async def _get_trusted_skill_pubkeys_map(rt: Optional[KernelRuntime]) -> Dict[str, str]:
    """
    Global trusted public keys for skill signature verification.
    Stored in global_setting: trusted_skill_pubkeys = {"keys":[{"key_id","public_key"}]}
    """
    from core.security.skill_signature_gate import get_trusted_skill_pubkeys_map

    return await get_trusted_skill_pubkeys_map(_store(rt))


async def _maybe_verify_and_audit_skill_signature(rt: Optional[KernelRuntime], *, skill: Any, scope: str) -> None:
    """
    Best-effort: compute verification status and record a changeset event.
    """
    try:
        meta = getattr(skill, "metadata", None)
        if not isinstance(meta, dict):
            return
        prov = meta.get("provenance") if isinstance(meta.get("provenance"), dict) else {}
        integ = meta.get("integrity") if isinstance(meta.get("integrity"), dict) else {}
        if not prov.get("signature") or not integ.get("bundle_sha256"):
            return

        trusted = await _get_trusted_skill_pubkeys_map(rt)
        mgr = _ws_skill_mgr(rt) if scope == "workspace" else _skill_mgr(rt)
        if not mgr:
            return
        prov2 = mgr.compute_skill_signature_verification(skill, trusted)
        if prov2:
            meta["provenance"] = prov2

        status = "success" if bool(prov2.get("signature_verified")) else "failed"
        if not trusted:
            status = "failed"
        await _record_changeset(
            rt,
            name="skill_signature_verify",
            target_type="skill",
            target_id=str(getattr(skill, "id", "") or ""),
            status=status,
            args={"scope": scope, "trusted_keys_count": len(trusted)},
            result={
                "bundle_sha256": integ.get("bundle_sha256"),
                "signature_verified": prov2.get("signature_verified"),
                "signature_verified_key_id": prov2.get("signature_verified_key_id"),
                "signature_verified_reason": prov2.get("signature_verified_reason"),
            },
        )
    except Exception:
        return


async def _require_skill_signature_gate_approval(
    rt: Optional[KernelRuntime],
    *,
    user_id: str,
    skill_id: str,
    action: str,
    details: str,
    metadata: Dict[str, Any],
) -> str:
    """
    Create approval request for unverified skill signature actions.
    """
    from core.security.skill_signature_gate import require_skill_signature_gate_approval

    mgr = _approval_mgr(rt)
    return await require_skill_signature_gate_approval(
        approval_manager=mgr,
        user_id=user_id,
        skill_id=skill_id,
        action=action,
        details=details,
        metadata=metadata,
    )


def _signature_gate_eval(*, metadata: Optional[Dict[str, Any]], trusted_keys_count: int) -> Dict[str, Any]:
    """
    Determine whether signature gate should trigger.
    Rule: require approval unless signature_verified == True.
    """
    from core.security.skill_signature_gate import signature_gate_eval

    return signature_gate_eval(metadata=metadata, trusted_keys_count=int(trusted_keys_count or 0))


def _is_approval_resolved_approved(rt: Optional[KernelRuntime], approval_request_id: str) -> bool:
    """
    Used for signature gate flows: check whether approval_request_id has been approved.
    """
    if not approval_request_id:
        return False
    mgr = _approval_mgr(rt)
    if not mgr:
        return False
    from core.harness.infrastructure.approval.types import RequestStatus

    r = mgr.get_request(str(approval_request_id))
    if not r:
        return False
    return r.status in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED)


def _reload_workspace_managers(rt: Optional[KernelRuntime]) -> None:
    """Delegate to core.workspace.reload and sync KernelRuntime in-place (best-effort)."""
    try:
        from core.workspace.reload import rebuild_workspace_managers

        out = rebuild_workspace_managers(
            engine_agent_manager=getattr(rt, "agent_manager", None) if rt else None,
            engine_skill_manager=getattr(rt, "skill_manager", None) if rt else None,
            engine_mcp_manager=getattr(rt, "mcp_manager", None) if rt else None,
        )
        if rt is not None:
            setattr(rt, "workspace_agent_manager", out.get("workspace_agent_manager"))
            setattr(rt, "workspace_skill_manager", out.get("workspace_skill_manager"))
            setattr(rt, "workspace_mcp_manager", out.get("workspace_mcp_manager"))
    except Exception:
        return


@router.get("/workspace/skills")
async def list_workspace_skills(
    category: Optional[str] = None,
    enabled_only: bool = False,
    status: Optional[str] = None,
    include_lint: bool = False,
    limit: int = 100,
    offset: int = 0,
    rt: RuntimeDep = None,
):
    """List workspace skills (~/.aiplat/skills)."""
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        return {"skills": [], "total": 0, "limit": limit, "offset": offset}
    skills = await mgr.list_skills(category, status, limit, offset)

    trusted_keys = await _get_trusted_skill_pubkeys_map(rt)
    result = []
    for s in skills:
        if enabled_only and s.status != "enabled":
            continue
        try:
            if trusted_keys and isinstance(getattr(s, "metadata", None), dict):
                prov2 = mgr.compute_skill_signature_verification(s, trusted_keys)
                if prov2:
                    s.metadata["provenance"] = prov2
        except Exception:
            pass
        item = {
            "id": s.id,
            "name": s.name,
            "category": s.type,
            "description": s.description,
            "status": s.status,
            "enabled": s.status == "enabled",
            "config": s.config or {},
            "input_schema": s.input_schema or {},
            "output_schema": s.output_schema or {},
            "metadata": s.metadata or {},
        }
        if include_lint:
            try:
                from core.management.skill_linter import lint_skill, lint_summary

                item["lint"] = lint_summary(lint_skill(s))
            except Exception:
                item["lint"] = {"risk_level": "low", "error_count": 0, "warning_count": 0, "blocked": False}
        result.append(item)
    return {"skills": result, "total": mgr.get_skill_count().get("total", 0), "limit": limit, "offset": offset}


@router.post("/workspace/skills")
async def create_workspace_skill(request: SkillCreateRequest, http_request: Request, rt: RuntimeDep = None):
    """Create a new workspace skill."""
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    deny = await rbac_guard(
        http_request=http_request,
        payload=request.model_dump() if hasattr(request, "model_dump") else {},
        action="create",
        resource_type="skill",
        resource_id=str(getattr(request, "name", "") or "") or None,
    )
    if deny:
        return deny
    try:
        md = request.metadata or {}
        # v2 field mapping: persist governance/routing fields into metadata so they survive reload
        if getattr(request, "skill_kind", None):
            md["skill_kind"] = request.skill_kind
        if getattr(request, "permissions", None) is not None:
            md["permissions"] = request.permissions
        if getattr(request, "trigger_conditions", None) is not None:
            md["trigger_conditions"] = request.trigger_conditions
        if getattr(request, "decision_tree", None) is not None:
            md["decision_tree"] = request.decision_tree
        if getattr(request, "resources", None) is not None:
            md["resources"] = request.resources
        # back-compat template + sop
        md["template"] = request.template
        md["sop"] = request.sop

        skill = await mgr.create_skill(
            name=str(getattr(request, "display_name", None) or request.name),
            skill_id=getattr(request, "skill_id", None),
            skill_type=request.category,
            description=request.description,
            config=request.config or {},
            input_schema=request.input_schema or {},
            output_schema=request.output_schema or {},
            metadata=md,
            version=getattr(request, "version", None),
            status=getattr(request, "status", None),
        )
        # Mark as pending verification (best-effort)
        eval_artifact_id: Optional[str] = None
        candidate_id: Optional[str] = None
        job_id = None
        try:
            await mgr.update_skill(
                str(skill.id),
                metadata={"verification": {"status": "pending", "updated_at": time.time(), "source": "autosmoke"}},
            )
        except Exception:
            pass
        # Create governance artifacts (best-effort): evaluation_report + release_candidate
        try:
            store = _store(rt)
            if store is not None:
                from core.learning.manager import LearningManager
                from core.learning.types import LearningArtifactKind

                lmgr = LearningManager(execution_store=store)
                sid = str(skill.id)
                job_id = f"autosmoke-skill:{sid}"
                eval_art = await lmgr.create_artifact(
                    kind=LearningArtifactKind.EVALUATION_REPORT,
                    target_type="skill",
                    target_id=sid,
                    version=f"autosmoke:{int(time.time())}",
                    status="pending",
                    payload={"source": "autosmoke", "job_id": job_id, "op": "create"},
                    metadata={"governance": True},
                )
                eval_artifact_id = eval_art.artifact_id
                cand = await lmgr.create_artifact(
                    kind=LearningArtifactKind.RELEASE_CANDIDATE,
                    target_type="skill",
                    target_id=sid,
                    version=str(getattr(skill, "version", "") or "v1.0.0"),
                    status="draft",
                    payload={"evaluation_artifact_id": eval_artifact_id},
                    metadata={"governance": True, "ready": False},
                )
                candidate_id = cand.artifact_id
                await mgr.update_skill(
                    sid,
                    metadata={
                        "governance": {
                            "status": "pending",
                            "evaluation_artifact_id": eval_artifact_id,
                            "candidate_id": candidate_id,
                            "job_id": job_id,
                            "last_op": "create",
                            "updated_at": time.time(),
                        }
                    },
                )
        except Exception:
            pass
        try:
            store = _store(rt)
            sched = _job_scheduler(rt)
            if store is not None and sched is not None:
                from core.harness.smoke import enqueue_autosmoke

                tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
                actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")
                sid = str(skill.id)

                async def _on_complete(job_run: Dict[str, Any]):
                    st = str(job_run.get("status") or "")
                    ver = {
                        "status": "verified" if st == "completed" else "failed",
                        "updated_at": time.time(),
                        "source": "autosmoke",
                        "job_id": job_id or f"autosmoke-skill:{sid}",
                        "job_run_id": str(job_run.get("id") or ""),
                        "reason": str(job_run.get("error") or ""),
                    }
                    try:
                        await mgr.update_skill(sid, metadata={"verification": ver})
                    except Exception:
                        pass
                    # Update governance artifacts (best-effort)
                    try:
                        if store is not None:
                            from core.learning.manager import LearningManager

                            lmgr = LearningManager(execution_store=store)
                            gid = eval_artifact_id
                            cid = candidate_id
                            if not gid or not cid:
                                # Try read from persisted frontmatter
                                s2 = await mgr.get_skill(sid)
                                g = (getattr(s2, "metadata", None) or {}).get("governance") if isinstance(getattr(s2, "metadata", None), dict) else {}
                                gid = g.get("evaluation_artifact_id")
                                cid = g.get("candidate_id")
                            if gid:
                                await lmgr.set_artifact_status(
                                    artifact_id=str(gid),
                                    status="verified" if st == "completed" else "failed",
                                    metadata_update={"job_run_id": str(job_run.get("id") or ""), "reason": str(job_run.get("error") or "")},
                                )
                            if cid:
                                await lmgr.set_artifact_status(
                                    artifact_id=str(cid),
                                    status="draft",
                                    metadata_update={"ready": bool(st == "completed"), "verification": ver, "job_run_id": str(job_run.get("id") or "")},
                                )
                            await mgr.update_skill(
                                sid,
                                metadata={"governance": {"status": "verified" if st == "completed" else "failed", "job_run_id": str(job_run.get("id") or ""), "updated_at": time.time()}},
                            )
                    except Exception:
                        pass

                await enqueue_autosmoke(
                    execution_store=store,
                    job_scheduler=sched,
                    resource_type="skill",
                    resource_id=sid,
                    tenant_id=tenant_id or "ops_smoke",
                    actor_id=actor_id or "admin",
                    detail={"op": "create", "name": skill.name},
                    on_complete=_on_complete,
                )
        except Exception:
            pass
        try:
            await _record_changeset(
                rt,
                name="skill_upsert",
                target_type="skill",
                target_id=str(skill.id),
                args={"scope": "workspace", "category": request.category, "name": request.name},
                result={
                    "status": "created",
                    "integrity": (getattr(skill, "metadata", None) or {}).get("integrity") if isinstance(getattr(skill, "metadata", None), dict) else None,
                    "provenance": (getattr(skill, "metadata", None) or {}).get("provenance") if isinstance(getattr(skill, "metadata", None), dict) else None,
                },
            )
        except Exception:
            pass
        try:
            await _maybe_verify_and_audit_skill_signature(rt, skill=skill, scope="workspace")
        except Exception:
            pass
        # Audit log (best-effort)
        try:
            store = _store(rt)
            if store is not None:
                actor = actor_from_http(http_request, request.model_dump() if hasattr(request, "model_dump") else {})
                await store.add_audit_log(
                    action="workspace_skill_create",
                    status="ok",
                    tenant_id=str(actor.get("tenant_id") or "") or None,
                    actor_id=str(actor.get("actor_id") or "") or None,
                    actor_role=str(actor.get("actor_role") or "") or None,
                    resource_type="skill",
                    resource_id=str(skill.id),
                    detail={"name": request.name, "category": request.category},
                )
        except Exception:
            pass
        lint = None
        try:
            from core.management.skill_linter import lint_skill

            lint = lint_skill(skill)
        except Exception:
            lint = None
        return {"id": skill.id, "status": "created", "name": skill.name, "lint": lint}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/workspace/skills/{skill_id}")
async def get_workspace_skill(skill_id: str, rt: RuntimeDep = None):
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await mgr.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return {
        "id": skill.id,
        "name": skill.name,
        "type": skill.type,
        "category": skill.type,
        "description": skill.description,
        "status": skill.status,
        "enabled": skill.status == "enabled",
        "config": skill.config or {},
        "input_schema": skill.input_schema or {},
        "output_schema": skill.output_schema or {},
        "metadata": skill.metadata or {},
    }


@router.put("/workspace/skills/{skill_id}")
async def update_workspace_skill(skill_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    from core.schemas import SkillUpdateRequest

    deny = await rbac_guard(http_request=http_request, payload=request or {}, action="update", resource_type="skill", resource_id=str(skill_id))
    if deny:
        return deny

    r = SkillUpdateRequest(**(request or {}))
    # NOTE: SkillManager.update_skill expects keyword fields; do not pass the dict as positional arg.
    skill = await mgr.update_skill(skill_id, **r.model_dump(exclude_unset=True))
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    # Mark as pending verification (best-effort)
    eval_artifact_id: Optional[str] = None
    candidate_id: Optional[str] = None
    job_id = None
    try:
        await mgr.update_skill(
            str(skill_id),
            metadata={"verification": {"status": "pending", "updated_at": time.time(), "source": "autosmoke"}},
        )
    except Exception:
        pass
    # Create governance artifacts (best-effort)
    try:
        store = _store(rt)
        if store is not None:
            from core.learning.manager import LearningManager
            from core.learning.types import LearningArtifactKind

            lmgr = LearningManager(execution_store=store)
            sid = str(skill_id)
            job_id = f"autosmoke-skill:{sid}"
            eval_art = await lmgr.create_artifact(
                kind=LearningArtifactKind.EVALUATION_REPORT,
                target_type="skill",
                target_id=sid,
                version=f"autosmoke:{int(time.time())}",
                status="pending",
                payload={"source": "autosmoke", "job_id": job_id, "op": "update"},
                metadata={"governance": True},
            )
            eval_artifact_id = eval_art.artifact_id
            cand = await lmgr.create_artifact(
                kind=LearningArtifactKind.RELEASE_CANDIDATE,
                target_type="skill",
                target_id=sid,
                version=str(getattr(skill, "version", "") or "v1.0.0"),
                status="draft",
                payload={"evaluation_artifact_id": eval_artifact_id},
                metadata={"governance": True, "ready": False},
            )
            candidate_id = cand.artifact_id
            await mgr.update_skill(
                sid,
                metadata={"governance": {"status": "pending", "evaluation_artifact_id": eval_artifact_id, "candidate_id": candidate_id, "job_id": job_id, "last_op": "update", "updated_at": time.time()}},
            )
    except Exception:
        pass
    try:
        store = _store(rt)
        sched = _job_scheduler(rt)
        if store is not None and sched is not None:
            from core.harness.smoke import enqueue_autosmoke

            tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
            actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")
            sid = str(skill_id)

            async def _on_complete(job_run: Dict[str, Any]):
                st = str(job_run.get("status") or "")
                ver = {
                    "status": "verified" if st == "completed" else "failed",
                    "updated_at": time.time(),
                    "source": "autosmoke",
                    "job_id": job_id or f"autosmoke-skill:{sid}",
                    "job_run_id": str(job_run.get("id") or ""),
                    "reason": str(job_run.get("error") or ""),
                }
                try:
                    await mgr.update_skill(sid, metadata={"verification": ver})
                except Exception:
                    pass
                try:
                    if store is not None:
                        from core.learning.manager import LearningManager

                        lmgr = LearningManager(execution_store=store)
                        gid = eval_artifact_id
                        cid = candidate_id
                        if not gid or not cid:
                            s2 = await mgr.get_skill(sid)
                            g = (getattr(s2, "metadata", None) or {}).get("governance") if isinstance(getattr(s2, "metadata", None), dict) else {}
                            gid = g.get("evaluation_artifact_id")
                            cid = g.get("candidate_id")
                        if gid:
                            await lmgr.set_artifact_status(
                                artifact_id=str(gid),
                                status="verified" if st == "completed" else "failed",
                                metadata_update={"job_run_id": str(job_run.get("id") or ""), "reason": str(job_run.get("error") or "")},
                            )
                        if cid:
                            await lmgr.set_artifact_status(
                                artifact_id=str(cid),
                                status="draft",
                                metadata_update={"ready": bool(st == "completed"), "verification": ver, "job_run_id": str(job_run.get("id") or "")},
                            )
                        await mgr.update_skill(
                            sid,
                            metadata={"governance": {"status": "verified" if st == "completed" else "failed", "job_run_id": str(job_run.get("id") or ""), "updated_at": time.time()}},
                        )
                except Exception:
                    pass

            await enqueue_autosmoke(
                execution_store=store,
                job_scheduler=sched,
                resource_type="skill",
                resource_id=sid,
                tenant_id=tenant_id or "ops_smoke",
                actor_id=actor_id or "admin",
                detail={"op": "update"},
                on_complete=_on_complete,
            )
    except Exception:
        pass
    try:
        await _record_changeset(
            rt,
            name="skill_upsert",
            target_type="skill",
            target_id=str(skill_id),
            args={"scope": "workspace", "fields": list(r.model_dump(exclude_unset=True).keys())[:50]},
            result={
                "status": "updated",
                "integrity": (getattr(skill, "metadata", None) or {}).get("integrity") if isinstance(getattr(skill, "metadata", None), dict) else None,
                "provenance": (getattr(skill, "metadata", None) or {}).get("provenance") if isinstance(getattr(skill, "metadata", None), dict) else None,
            },
        )
    except Exception:
        pass
    try:
        await _maybe_verify_and_audit_skill_signature(rt, skill=skill, scope="workspace")
    except Exception:
        pass
    # Audit log (best-effort)
    try:
        store = _store(rt)
        if store is not None:
            actor = actor_from_http(http_request, request or {})
            await store.add_audit_log(
                action="workspace_skill_update",
                status="ok",
                tenant_id=str(actor.get("tenant_id") or "") or None,
                actor_id=str(actor.get("actor_id") or "") or None,
                actor_role=str(actor.get("actor_role") or "") or None,
                resource_type="skill",
                resource_id=str(skill_id),
                detail={"fields": list((r.model_dump(exclude_unset=True) or {}).keys())},
            )
    except Exception:
        pass
    lint = None
    try:
        from core.management.skill_linter import lint_skill

        lint = lint_skill(skill)
    except Exception:
        lint = None
    return {"status": "updated", "id": skill_id, "lint": lint}


async def _skill_routing_funnel(
    rt: Optional[KernelRuntime],
    *,
    tenant_id: Optional[str],
    since_hours: int,
    limit: int,
    coding_policy_profile: Optional[str] = None,
) -> Dict[str, Any]:
    # Deprecated wrapper: logic lives in core.observability.routing_service.
    from core.observability.routing_service import skill_routing_funnel

    return await skill_routing_funnel(store=_store(rt), tenant_id=tenant_id, since_hours=since_hours, limit=limit, coding_policy_profile=coding_policy_profile)


def _skill_tokenize_for_conflict(skill: Any) -> Dict[str, Any]:
    """Best-effort tokenization for conflict detection (no external deps)."""
    try:
        sid = str(getattr(skill, "id", "") or (skill.get("id") if isinstance(skill, dict) else "") or "")
    except Exception:
        sid = ""
    name = str(getattr(skill, "name", "") or (skill.get("name") if isinstance(skill, dict) else "") or "")
    meta = getattr(skill, "metadata", None) if not isinstance(skill, dict) else skill.get("metadata")
    meta = meta if isinstance(meta, dict) else {}
    tc = meta.get("trigger_conditions") or meta.get("trigger_keywords") or []
    kw = meta.get("keywords") if isinstance(meta.get("keywords"), dict) else {}
    neg = meta.get("negative_triggers") or []

    def _norm(x: str) -> str:
        s = str(x or "").strip().lower()
        s = re.sub(r"[\s\-\._/]+", " ", s)
        s = re.sub(r"[^\w\u4e00-\u9fff ]+", "", s)
        return s.strip()

    tokens = set()
    for it in (tc if isinstance(tc, list) else [tc]):
        s = _norm(str(it))
        if not s:
            continue
        # keep whole phrase and split words
        tokens.add(s)
        for w in s.split():
            if len(w) >= 2:
                tokens.add(w)
    for k in ("objects", "actions", "constraints", "synonyms"):
        for it in (kw.get(k) or []) if isinstance(kw, dict) else []:
            s = _norm(str(it))
            if s:
                tokens.add(s)
    for it in (neg if isinstance(neg, list) else [neg]):
        s = _norm(str(it))
        if s:
            # negative triggers help reduce conflict; still keep for overlap explain
            tokens.add(s)
    return {"skill_id": sid, "name": name, "tokens": sorted(list(tokens))}


async def _enrich_conflicts_for_skill(
    rt: Optional[KernelRuntime],
    *,
    skill_id: str,
    raw_items: list,
) -> list:
    """
    Enrich conflict items with the opponent skill's detail (best-effort).
    This is used only for lint/fix generation (not persisted).
    """
    try:
        mgr = _ws_skill_mgr(rt)
        if mgr is None:
            return raw_items
        out = []
        for it in raw_items or []:
            if not isinstance(it, dict):
                continue
            a = (it.get("skill_a") or {}) if isinstance(it.get("skill_a"), dict) else {}
            b = (it.get("skill_b") or {}) if isinstance(it.get("skill_b"), dict) else {}
            a_id = str(a.get("skill_id") or "")
            b_id = str(b.get("skill_id") or "")
            other_id = b_id if a_id == str(skill_id) else a_id
            other = None
            try:
                if other_id:
                    other = await mgr.get_skill(other_id)
            except Exception:
                other = None
            other_meta = (getattr(other, "metadata", None) or {}) if other is not None and isinstance(getattr(other, "metadata", None), dict) else {}
            other_obj = {
                "skill_id": other_id,
                "name": str(getattr(other, "name", "") or other_id),
                "trigger_conditions": other_meta.get("trigger_conditions") or [],
                "negative_triggers": other_meta.get("negative_triggers") or [],
                "keywords": other_meta.get("keywords") if isinstance(other_meta.get("keywords"), dict) else {},
                "description": str(getattr(other, "description", "") or ""),
            }
            it2 = dict(it)
            it2["other_skill"] = other_obj
            out.append(it2)
        return out
    except Exception:
        return raw_items


async def _lint_conflicts_workspace_skills(
    rt: Optional[KernelRuntime],
    *,
    tenant_id: Optional[str] = None,
    threshold: float = 0.35,
    min_overlap: int = 3,
    limit: int = 100,
) -> Dict[str, Any]:
    """Detect likely routing conflicts among workspace skills."""
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    # reuse tenant_id only for future multi-tenant segregation; workspace skills are tenant-scoped by storage anyway
    _ = tenant_id
    threshold = float(threshold or 0.35)
    min_overlap = max(1, int(min_overlap or 3))
    limit = max(1, min(int(limit or 100), 500))

    skills = await mgr.list_skills(None, None, 500, 0)
    rows = [_skill_tokenize_for_conflict(s) for s in (skills or [])]
    conflicts = []
    for i in range(len(rows)):
        a = rows[i]
        ta = set(a["tokens"])
        if not ta:
            continue
        for j in range(i + 1, len(rows)):
            b = rows[j]
            tb = set(b["tokens"])
            if not tb:
                continue
            inter = ta & tb
            if len(inter) < min_overlap:
                continue
            uni = ta | tb
            score = float(len(inter) / max(1, len(uni)))
            if score < threshold:
                continue
            conflicts.append(
                {
                    "scope": "workspace",
                    "skill_a": {"skill_id": a["skill_id"], "name": a["name"]},
                    "skill_b": {"skill_id": b["skill_id"], "name": b["name"]},
                    "jaccard": score,
                    "overlap_tokens": sorted(list(inter))[:30],
                    "suggestions": [
                        "为两者补充 negative_triggers（明确不适用场景）",
                        "为其中一个补充 constraints（如：按租户/按项目/仅后端/仅SQL）以提高区分度",
                        "补齐 keywords.objects/actions，减少泛化描述",
                    ],
                }
            )
    conflicts.sort(key=lambda x: float(x.get("jaccard") or 0.0), reverse=True)
    return {"status": "ok", "items": conflicts[:limit], "total": len(conflicts), "threshold": threshold, "min_overlap": min_overlap}


@router.get("/workspace/skills/{skill_id}/lint")
async def lint_workspace_skill(skill_id: str, rt: RuntimeDep = None):
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    s = await mgr.get_skill(skill_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    from core.management.skill_linter import lint_skill, propose_skill_fixes

    # Attach observability hint (best-effort) for routing-quality fixes
    try:
        fun = await _skill_routing_funnel(rt, tenant_id=None, since_hours=24, limit=20000)
        row = next((x for x in (fun.get("items") or []) if str(x.get("name") or "") == str(skill_id)), None)
        if row:
            md = s.metadata if isinstance(getattr(s, "metadata", None), dict) else {}
            md = {**md, "_observability": {"scope": "workspace", **row}}
            try:
                s.metadata = md
            except Exception:
                pass
    except Exception:
        pass

    # Attach conflict hints (best-effort): inject top conflict pairs for this skill
    try:
        conf = await _lint_conflicts_workspace_skills(rt, tenant_id=None, threshold=0.2, min_overlap=2, limit=200)
        items = conf.get("items") if isinstance(conf, dict) else None
        items = items if isinstance(items, list) else []
        related = []
        for it in items:
            if not isinstance(it, dict):
                continue
            a = (it.get("skill_a") or {}) if isinstance(it.get("skill_a"), dict) else {}
            b = (it.get("skill_b") or {}) if isinstance(it.get("skill_b"), dict) else {}
            if str(a.get("skill_id") or "") == str(skill_id) or str(b.get("skill_id") or "") == str(skill_id):
                related.append(it)
        related.sort(key=lambda x: float(x.get("jaccard") or 0.0), reverse=True)
        if related:
            related = await _enrich_conflicts_for_skill(rt, skill_id=str(skill_id), raw_items=related[:5])
            md = s.metadata if isinstance(getattr(s, "metadata", None), dict) else {}
            md = {**md, "_conflicts": related}
            try:
                s.metadata = md
            except Exception:
                pass
    except Exception:
        pass

    lint = lint_skill(s)
    fixes = propose_skill_fixes(skill=s, lint=lint)
    return {"skill_id": str(skill_id), "lint": lint, "fixes": fixes.get("fixes") or [], "fix_summary": fixes.get("summary") or {}}


@router.post("/workspace/skills/{skill_id}/apply-lint-fix")
async def apply_lint_fix_workspace_skill(
    skill_id: str,
    request: Optional[Dict[str, Any]] = None,
    http_request: Request = None,
    rt: RuntimeDep = None,
):
    """Apply lint fixes to a workspace skill (Phase-2: metadata/trigger fixes supported)."""
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    req = request or {}
    dry_run = bool(req.get("dry_run", False))

    deny = None
    try:
        if http_request is not None:
            deny = await rbac_guard(
                http_request=http_request,
                payload=req,
                action="update",
                resource_type="skill",
                resource_id=str(skill_id),
            )
    except Exception:
        deny = None
    if deny:
        return deny

    s = await mgr.get_skill(skill_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")

    from core.management.skill_linter import lint_skill, propose_skill_fixes

    # Attach observability hint to allow routing-related fixes by issue_code
    try:
        fun = await _skill_routing_funnel(rt, tenant_id=None, since_hours=24, limit=20000)
        row = next((x for x in (fun.get("items") or []) if str(x.get("name") or "") == str(skill_id)), None)
        if row:
            md = s.metadata if isinstance(getattr(s, "metadata", None), dict) else {}
            md = {**md, "_observability": {"scope": "workspace", **row}}
            try:
                s.metadata = md
            except Exception:
                pass
    except Exception:
        pass

    # Attach conflict hints (best-effort) for conflict-pair disambiguation fixes
    try:
        conf = await _lint_conflicts_workspace_skills(rt, tenant_id=None, threshold=0.2, min_overlap=2, limit=200)
        items = conf.get("items") if isinstance(conf, dict) else None
        items = items if isinstance(items, list) else []
        related = []
        for it in items:
            if not isinstance(it, dict):
                continue
            a = (it.get("skill_a") or {}) if isinstance(it.get("skill_a"), dict) else {}
            b = (it.get("skill_b") or {}) if isinstance(it.get("skill_b"), dict) else {}
            if str(a.get("skill_id") or "") == str(skill_id) or str(b.get("skill_id") or "") == str(skill_id):
                related.append(it)
        related.sort(key=lambda x: float(x.get("jaccard") or 0.0), reverse=True)
        if related:
            related = await _enrich_conflicts_for_skill(rt, skill_id=str(skill_id), raw_items=related[:5])
            md = s.metadata if isinstance(getattr(s, "metadata", None), dict) else {}
            md = {**md, "_conflicts": related}
            try:
                s.metadata = md
            except Exception:
                pass
    except Exception:
        pass

    lint = lint_skill(s)
    fx = propose_skill_fixes(skill=s, lint=lint)
    fixes = fx.get("fixes") or []

    want_fix_ids = {str(x).strip() for x in (req.get("fix_ids") or []) if str(x).strip()}
    want_issue_codes = {str(x).strip() for x in (req.get("issue_codes") or []) if str(x).strip()}
    if not want_fix_ids and not want_issue_codes:
        selected = [f for f in fixes if bool(f.get("auto_applicable"))]
    else:
        selected = []
        for f in fixes:
            if want_fix_ids and str(f.get("fix_id") or "") in want_fix_ids:
                selected.append(f)
                continue
            if want_issue_codes and str(f.get("issue_code") or "") in want_issue_codes:
                selected.append(f)
                continue

    # Allowed patch paths (workspace only).
    allowed_paths = {
        ("output_schema", "markdown"),
        ("output_schema", "change_plan"),
        ("output_schema", "changed_files"),
        ("output_schema", "unrelated_changes"),
        ("output_schema", "acceptance_criteria"),
        ("output_schema", "rollback_plan"),
        ("description",),
        ("name",),
        ("trigger_conditions",),
        ("negative_triggers",),
        ("required_questions",),
        ("keywords",),
        ("permissions",),
    }

    ops = []
    for f in selected:
        patch = f.get("patch") if isinstance(f.get("patch"), dict) else {}
        if str(patch.get("format") or "") != "frontmatter_merge":
            continue
        for op in patch.get("ops") if isinstance(patch.get("ops"), list) else []:
            if not isinstance(op, dict):
                continue
            if op.get("op") != "upsert":
                continue
            path = op.get("path")
            if not isinstance(path, list) or not path:
                continue
            tpath = tuple(str(x) for x in path)
            if tpath not in allowed_paths:
                continue
            ops.append(op)

    if dry_run:
        return {"status": "dry_run", "skill_id": str(skill_id), "selected": selected, "ops": ops}
    if not ops:
        return {"status": "noop", "skill_id": str(skill_id), "selected": selected, "ops": []}

    out_patch: Dict[str, Any] = {}
    meta_patch: Dict[str, Any] = {}
    name_patch: Optional[str] = None
    desc_patch: Optional[str] = None
    for op in ops:
        v = op.get("value")
        path = op.get("path") if isinstance(op.get("path"), list) else []
        if path == ["output_schema", "markdown"] and isinstance(v, dict):
            out_patch["markdown"] = v
            continue
        if len(path) == 2 and path[0] == "output_schema" and isinstance(path[1], str) and isinstance(v, dict):
            out_patch[str(path[1])] = v
            continue
        if path == ["name"] and isinstance(v, str):
            name_patch = v
            continue
        if path == ["description"] and isinstance(v, str):
            desc_patch = v
            continue
        if path and path[0] in ("trigger_conditions", "negative_triggers", "required_questions", "keywords", "permissions"):
            meta_patch[str(path[0])] = v

    skill2 = await mgr.update_skill(
        skill_id,
        name=name_patch,
        description=desc_patch,
        metadata=meta_patch if meta_patch else None,
        output_schema=out_patch if out_patch else None,
    )
    if not skill2:
        raise HTTPException(status_code=500, detail="Failed to update skill")

    lint2 = lint_skill(skill2)
    fx2 = propose_skill_fixes(skill=skill2, lint=lint2)
    return {
        "status": "applied",
        "skill_id": str(skill_id),
        "selected_fix_ids": [str(f.get("fix_id") or "") for f in selected],
        "lint": lint2,
        "fixes": fx2.get("fixes") or [],
        "fix_summary": fx2.get("summary") or {},
    }


@router.post("/workspace/skills/lint-scan")
async def lint_scan_workspace_skills(request: Optional[dict] = None, rt: RuntimeDep = None):
    """
    Lint-scan workspace skills (for cron / ops). Best-effort and side-effect free.
    """
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    req = request or {}
    category = str(req.get("category") or "").strip() or None
    status = str(req.get("status") or "").strip() or None
    limit = int(req.get("limit") or 200)
    offset = int(req.get("offset") or 0)
    include_full = bool(req.get("include_full", False))

    from core.management.skill_linter import lint_skill, lint_summary

    skills = await mgr.list_skills(category, status, limit, offset)
    items = []
    for s in skills:
        rep = lint_skill(s)
        items.append({"skill_id": s.id, "name": s.name, "summary": lint_summary(rep), "lint": rep if include_full else None})
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.get("/workspace/skills/meta/lint-conflicts")
async def lint_conflicts_workspace_skills(
    tenant_id: Optional[str] = None,
    threshold: float = 0.35,
    min_overlap: int = 3,
    limit: int = 100,
    rt: RuntimeDep = None,
):
    return await _lint_conflicts_workspace_skills(rt, tenant_id=tenant_id, threshold=threshold, min_overlap=min_overlap, limit=limit)


async def _skill_invocation_metrics(rt: Optional[KernelRuntime], *, tenant_id: Optional[str], since_hours: int, limit: int) -> Dict[str, Any]:
    store = _store(rt)
    if not store:
        return {"items": [], "total": 0}
    since_hours = max(1, min(int(since_hours or 24), 24 * 30))
    limit = max(100, min(int(limit or 5000), 20000))
    now = time.time()
    cutoff = now - since_hours * 3600
    res = await store.list_syscall_events(limit=limit, offset=0, tenant_id=tenant_id, kind="skill")
    items = res.get("items") or []
    # filter by cutoff
    items = [it for it in items if float(it.get("created_at") or 0) >= cutoff]
    by_name: Dict[str, Any] = {}
    for it in items:
        nm = str(it.get("name") or "<unknown>")
        st = str(it.get("status") or "unknown")
        dur = float(it.get("duration_ms") or 0.0)
        x = by_name.setdefault(nm, {"name": nm, "total": 0, "counts": {}, "avg_duration_ms": 0.0, "p95_duration_ms": None, "durations_ms": []})
        x["total"] += 1
        x["counts"][st] = int(x["counts"].get(st, 0)) + 1
        if dur > 0:
            x["durations_ms"].append(dur)
    out = []
    for nm, x in by_name.items():
        durs = sorted(x.get("durations_ms") or [])
        avg = float(sum(durs) / len(durs)) if durs else 0.0
        p95 = None
        if durs:
            idx = int(max(0, min(len(durs) - 1, round(0.95 * (len(durs) - 1)))))
            p95 = float(durs[idx])
        out.append({"name": nm, "total": x["total"], "counts": x["counts"], "avg_duration_ms": avg, "p95_duration_ms": p95})
    out.sort(key=lambda r: int(r.get("total") or 0), reverse=True)
    return {"items": out, "total": len(out), "since_hours": since_hours}


@router.get("/workspace/skills/observability/skill-metrics")
async def workspace_skill_metrics(tenant_id: Optional[str] = None, since_hours: int = 24, limit: int = 5000, rt: RuntimeDep = None):
    """Aggregate syscall_events(kind=skill) into a skill-level metrics view."""
    return {"status": "ok", **(await _skill_invocation_metrics(rt, tenant_id=tenant_id, since_hours=since_hours, limit=limit))}


@router.delete("/workspace/skills/{skill_id}")
async def delete_workspace_skill(skill_id: str, delete_files: bool = False, http_request: Request = None, rt: RuntimeDep = None):
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    if http_request is not None:
        deny = await rbac_guard(
            http_request=http_request,
            payload={"delete_files": bool(delete_files)},
            action="delete",
            resource_type="skill",
            resource_id=str(skill_id),
        )
        if deny:
            return deny
    ok = await mgr.delete_skill(skill_id, delete_files=delete_files)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    try:
        store = _store(rt)
        if store is not None and http_request is not None:
            actor = actor_from_http(http_request, {"delete_files": bool(delete_files)})
            await store.add_audit_log(
                action="workspace_skill_delete",
                status="ok",
                tenant_id=str(actor.get("tenant_id") or "") or None,
                actor_id=str(actor.get("actor_id") or "") or None,
                actor_role=str(actor.get("actor_role") or "") or None,
                resource_type="skill",
                resource_id=str(skill_id),
                detail={"delete_files": bool(delete_files)},
            )
    except Exception:
        pass
    return {"status": "deleted", "id": skill_id, "delete_files": delete_files}


@router.post("/workspace/skills/{skill_id}/enable")
async def enable_workspace_skill(skill_id: str, request: Optional[Dict[str, Any]] = None, http_request: Request = None, rt: RuntimeDep = None):
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    req = request or {}
    if http_request is not None:
        deny = await rbac_guard(http_request=http_request, payload=req if isinstance(req, dict) else {}, action="enable", resource_type="skill", resource_id=str(skill_id))
        if deny:
            return deny
    actor0 = actor_from_http(http_request, req if isinstance(req, dict) else None) if http_request is not None else {"actor_id": "admin"}
    change_id = _new_change_id()
    approval_request_id = str(req.get("approval_request_id") or "").strip() or None
    details = str(req.get("details") or "").strip()

    # Change-control gate (best-effort)
    try:
        from core.governance.gating import autosmoke_enforce, gate_with_change_control

        if autosmoke_enforce(store=_store(rt)):
            change_id = await gate_with_change_control(
                store=_store(rt),
                operation="workspace.skill.enable",
                targets=[("skill", str(skill_id))],
                actor=actor0,
                approval_request_id=approval_request_id,
                workspace_agent_manager=_ws_agent_mgr(rt),
                workspace_skill_manager=mgr,
                skill_manager=_skill_mgr(rt),
                workspace_mcp_manager=_ws_mcp_mgr(rt),
                mcp_manager=_mcp_mgr(rt),
            )
    except HTTPException:
        raise
    except Exception:
        pass

    # Signature gate: unverified workspace skills require approval to enable.
    s = await mgr.get_skill(skill_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")

    # Skill lint gate (graded): high-risk + lint errors -> block enable. Others: allow with warnings.
    lint = None
    lint_sum = None
    try:
        from core.management.skill_linter import lint_skill, lint_summary

        lint = lint_skill(s)
        lint_sum = lint_summary(lint)
        if lint_sum.get("blocked") is True:
            try:
                await _record_changeset(
                    rt,
                    name="skill_lint_gate",
                    target_type="skill",
                    target_id=str(skill_id),
                    status="blocked",
                    args={"scope": "workspace", "action": "enable", "risk_level": lint_sum.get("risk_level")},
                    result={"lint": lint_sum, "reason": "high_risk_lint_errors"},
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="skill_lint_blocked",
                    message="skill_lint_blocked",
                    approval_request_id=None,
                    next_actions=[
                        {"type": "open_skill", "label": "查看 Skill", "url": ui_url("/workspace/skills")},
                        {"type": "lint", "label": "查看 Lint 报告", "url": ui_url("/workspace/skills"), "skill_id": str(skill_id)},
                    ],
                ),
            )
    except HTTPException:
        raise
    except Exception:
        lint = None
        lint_sum = None

    # Publish gate: if governance candidate exists, require it to be published before enabling.
    pg = _governance_publish_gate(getattr(s, "metadata", None))
    if pg.get("required") is True:
        try:
            await _record_changeset(
                rt,
                name="skill_publish_gate",
                target_type="skill",
                target_id=str(skill_id),
                status="blocked",
                args={"scope": "workspace", "action": "enable", "candidate_id": pg.get("candidate_id")},
                result={"reason": "publish_required"},
            )
        except Exception:
            pass
        return {"status": "publish_required", "candidate_id": pg.get("candidate_id"), "releases_url": ui_url("/core/learning/releases"), "change_id": change_id, "links": governance_links(change_id=change_id)}

    trusted = await _get_trusted_skill_pubkeys_map(rt)
    try:
        prov2 = mgr.compute_skill_signature_verification(s, trusted)
        if isinstance(getattr(s, "metadata", None), dict) and prov2:
            s.metadata["provenance"] = prov2
    except Exception:
        prov2 = (getattr(s, "metadata", None) or {}).get("provenance") if isinstance(getattr(s, "metadata", None), dict) else {}

    gate = _signature_gate_eval(metadata=getattr(s, "metadata", None), trusted_keys_count=len(trusted))
    if gate.get("required") is True:
        if not approval_request_id:
            rid = await _require_skill_signature_gate_approval(
                rt,
                user_id="admin",
                skill_id=str(skill_id),
                action="enable",
                details=details or f"enable workspace skill {skill_id}",
                metadata={
                    "skill_id": str(skill_id),
                    "action": "enable",
                    "reason": gate.get("reason"),
                    "provenance": (getattr(s, "metadata", None) or {}).get("provenance") if isinstance(getattr(s, "metadata", None), dict) else {},
                    "integrity": (getattr(s, "metadata", None) or {}).get("integrity") if isinstance(getattr(s, "metadata", None), dict) else {},
                },
            )
            try:
                await _record_changeset(
                    rt,
                    name="skill_signature_gate",
                    target_type="skill",
                    target_id=str(skill_id),
                    status="approval_required",
                    args={"scope": "workspace", "action": "enable", "reason": gate.get("reason")},
                    approval_request_id=rid,
                )
            except Exception:
                pass
            try:
                await _record_changeset(
                    rt,
                    name="workspace.skill.enable",
                    target_type="change",
                    target_id=change_id,
                    status="approval_required",
                    args={"targets": [{"type": "skill", "id": str(skill_id)}], "reason": "signature_gate"},
                    approval_request_id=rid,
                    user_id=str(actor0.get("actor_id") or "admin"),
                    tenant_id=str(actor0.get("tenant_id") or "") or None,
                    session_id=str(actor0.get("session_id") or "") or None,
                )
            except Exception:
                pass
            return {"status": "approval_required", "approval_request_id": rid, "change_id": change_id, "links": governance_links(change_id=change_id, approval_request_id=rid)}
        if not _is_approval_resolved_approved(rt, approval_request_id):
            try:
                await _record_changeset(
                    rt,
                    name="skill_signature_gate",
                    target_type="skill",
                    target_id=str(skill_id),
                    status="failed",
                    args={"scope": "workspace", "action": "enable", "reason": gate.get("reason")},
                    error="not_approved",
                    approval_request_id=approval_request_id,
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message="not_approved",
                    approval_request_id=str(approval_request_id),
                    next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(approval_request_id)}],
                ),
            )
        try:
            await _record_changeset(rt, name="skill_signature_gate", target_type="skill", target_id=str(skill_id), status="success", args={"scope": "workspace", "action": "enable"}, approval_request_id=approval_request_id)
        except Exception:
            pass

    ok = await mgr.enable_skill(skill_id)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Skill {skill_id} cannot be enabled (maybe deprecated; use restore)")
    try:
        await _record_changeset(
            rt,
            name="workspace.skill.enable",
            target_type="change",
            target_id=change_id,
            status="success",
            args={"targets": [{"type": "skill", "id": str(skill_id)}]},
            approval_request_id=approval_request_id,
            user_id=str(actor0.get("actor_id") or "admin"),
            tenant_id=str(actor0.get("tenant_id") or "") or None,
            session_id=str(actor0.get("session_id") or "") or None,
        )
    except Exception:
        pass
    try:
        store = _store(rt)
        if store is not None and http_request is not None:
            actor = actor_from_http(http_request, req if isinstance(req, dict) else {})
            await store.add_audit_log(
                action="workspace_skill_enable",
                status="ok",
                tenant_id=str(actor.get("tenant_id") or "") or None,
                actor_id=str(actor.get("actor_id") or "") or None,
                actor_role=str(actor.get("actor_role") or "") or None,
                resource_type="skill",
                resource_id=str(skill_id),
                detail={"approval_request_id": approval_request_id, "change_id": change_id},
            )
    except Exception:
        pass
    return {
        "status": "enabled",
        "approval_request_id": approval_request_id,
        "change_id": change_id,
        "lint": lint,
        "lint_summary": lint_sum,
        "links": governance_links(change_id=change_id, approval_request_id=str(approval_request_id) if approval_request_id else None),
    }


@router.post("/workspace/skills/{skill_id}/disable")
async def disable_workspace_skill(skill_id: str, http_request: Request = None, rt: RuntimeDep = None):
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    if http_request is not None:
        deny = await rbac_guard(http_request=http_request, payload={}, action="disable", resource_type="skill", resource_id=str(skill_id))
        if deny:
            return deny
    ok = await mgr.disable_skill(skill_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    try:
        store = _store(rt)
        if store is not None and http_request is not None:
            actor = actor_from_http(http_request, {})
            await store.add_audit_log(
                action="workspace_skill_disable",
                status="ok",
                tenant_id=str(actor.get("tenant_id") or "") or None,
                actor_id=str(actor.get("actor_id") or "") or None,
                actor_role=str(actor.get("actor_role") or "") or None,
                resource_type="skill",
                resource_id=str(skill_id),
                detail={},
            )
    except Exception:
        pass
    return {"status": "disabled"}


@router.post("/workspace/skills/{skill_id}/restore")
async def restore_workspace_skill(skill_id: str, http_request: Request = None, rt: RuntimeDep = None):
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    if http_request is not None:
        deny = await rbac_guard(http_request=http_request, payload={}, action="restore", resource_type="skill", resource_id=str(skill_id))
        if deny:
            return deny
    ok = await mgr.restore_skill(skill_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    try:
        store = _store(rt)
        if store is not None and http_request is not None:
            actor = actor_from_http(http_request, {})
            await store.add_audit_log(
                action="workspace_skill_restore",
                status="ok",
                tenant_id=str(actor.get("tenant_id") or "") or None,
                actor_id=str(actor.get("actor_id") or "") or None,
                actor_role=str(actor.get("actor_role") or "") or None,
                resource_type="skill",
                resource_id=str(skill_id),
                detail={},
            )
    except Exception:
        pass
    return {"status": "enabled"}


@router.get("/workspace/skills/{skill_id}/revisions")
async def list_workspace_skill_revisions(skill_id: str, limit: int = 50, offset: int = 0, rt: RuntimeDep = None):
    """List revision snapshots for a workspace skill (best-effort)."""
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await mgr.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")

    skill_dir = None
    try:
        fs = skill.metadata.get("filesystem") if isinstance(skill.metadata, dict) else None
        if isinstance(fs, dict) and fs.get("skill_dir"):
            skill_dir = Path(str(fs.get("skill_dir")))
    except Exception:
        skill_dir = None
    if skill_dir is None:
        # best effort fallback
        base = mgr._resolve_skills_base_path()  # type: ignore[attr-defined]
        skill_dir = Path(base) / skill_id

    rev_root = skill_dir / ".revisions"
    if not rev_root.exists():
        return {"items": [], "total": 0, "limit": limit, "offset": offset}
    revs = sorted([p.name for p in rev_root.iterdir() if p.is_dir()], reverse=True)
    total = len(revs)
    page = revs[offset : offset + limit]
    return {"items": page, "total": total, "limit": limit, "offset": offset}


@router.get("/workspace/skills/{skill_id}/files")
async def list_workspace_skill_files(skill_id: str, dir: str = "references", rt: RuntimeDep = None):
    """List files under workspace skill directory (references/scripts/assets)."""
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await mgr.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")

    base = mgr._resolve_skills_base_path()  # type: ignore[attr-defined]
    skill_dir = Path(base) / skill_id
    allow = {"references", "scripts", "assets"}
    if dir not in allow:
        raise HTTPException(status_code=400, detail=f"dir must be one of {sorted(list(allow))}")
    root = (skill_dir / dir).resolve()
    if not root.exists():
        return {"items": [], "total": 0}

    items = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        try:
            rel = str(p.relative_to(skill_dir))
        except Exception:
            continue
        st = p.stat()
        items.append({"path": rel, "size": int(st.st_size), "mtime": float(st.st_mtime)})
    items.sort(key=lambda x: x["path"])
    return {"items": items, "total": len(items)}


@router.get("/workspace/skills/{skill_id}/files/{rel_path:path}")
async def get_workspace_skill_file(skill_id: str, rel_path: str, rt: RuntimeDep = None):
    """Fetch a workspace skill file content (text only, best-effort)."""
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")

    base = mgr._resolve_skills_base_path()  # type: ignore[attr-defined]
    skill_dir = (Path(base) / skill_id).resolve()
    p = (skill_dir / rel_path).resolve()
    # enforce allowed subpaths
    allowed_roots = [(skill_dir / "references").resolve(), (skill_dir / "scripts").resolve(), (skill_dir / "assets").resolve(), (skill_dir / ".revisions").resolve()]
    if not any(str(p).startswith(str(r)) for r in allowed_roots):
        raise HTTPException(status_code=403, detail="path not allowed")
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    # small text only
    data = p.read_bytes()
    if len(data) > 200_000:
        raise HTTPException(status_code=413, detail="file too large")
    try:
        text = data.decode("utf-8")
    except Exception:
        raise HTTPException(status_code=415, detail="binary file not supported")
    return {"path": rel_path, "content": text}


@router.post("/workspace/skills/{skill_id}/execute")
async def execute_workspace_skill(skill_id: str, request: SkillExecuteRequest, http_request: Request, rt: RuntimeDep = None):
    """Execute workspace skill."""
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await mgr.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")

    # Publish gate: if governance candidate exists, require it to be published before executing.
    pg = _governance_publish_gate(getattr(skill, "metadata", None))
    if pg.get("required") is True:
        try:
            await _record_changeset(
                rt,
                name="skill_publish_gate",
                target_type="skill",
                target_id=str(skill_id),
                status="blocked",
                args={"scope": "workspace", "action": "execute", "candidate_id": pg.get("candidate_id")},
                result={"reason": "publish_required"},
            )
        except Exception:
            pass
        # PR-02: Run Contract v2 (blocked)
        resp = {
            "ok": False,
            "run_id": new_prefixed_id("run"),
            "trace_id": None,
            "status": RunStatus.aborted.value,
            "legacy_status": "publish_required",
            "output": None,
            "error": {"code": "PUBLISH_REQUIRED", "message": "publish_required", "detail": {"candidate_id": pg.get("candidate_id")}},
            "candidate_id": pg.get("candidate_id"),
            "releases_url": ui_url("/core/learning/releases"),
        }
        try:
            await _audit_execute(rt, http_request=http_request, payload={"context": {}}, resource_type="skill", resource_id=str(skill_id), resp=resp, action="execute_skill")
        except Exception:
            pass
        return resp

    # Merge platform identity headers into context (best-effort)
    ctx_for_user: Dict[str, Any] = dict(request.context or {}) if isinstance(request.context, dict) else {}
    try:
        tmp = _inject_http_request_context({"context": dict(ctx_for_user)}, http_request, entrypoint="api")
        ctx_for_user = tmp.get("context") if isinstance(tmp, dict) and isinstance(tmp.get("context"), dict) else ctx_for_user
    except Exception:
        pass

    deny = await rbac_guard(http_request=http_request, payload={"context": ctx_for_user}, action="execute", resource_type="skill", resource_id=str(skill_id))
    if deny:
        return deny

    # Signature gate: unverified workspace skills require approval to execute.
    try:
        opts = request.options if isinstance(getattr(request, "options", None), dict) else {}
    except Exception:
        opts = {}
    approval_request_id = None
    details = ""
    try:
        approval_request_id = str(opts.get("approval_request_id") or "").strip() or None
        details = str(opts.get("details") or "").strip()
    except Exception:
        approval_request_id = None
        details = ""

    trusted = await _get_trusted_skill_pubkeys_map(rt)
    try:
        prov2 = mgr.compute_skill_signature_verification(skill, trusted)
        if isinstance(getattr(skill, "metadata", None), dict) and prov2:
            skill.metadata["provenance"] = prov2
    except Exception:
        pass
    gate = _signature_gate_eval(metadata=getattr(skill, "metadata", None), trusted_keys_count=len(trusted))
    if gate.get("required") is True:
        if not approval_request_id:
            rid = await _require_skill_signature_gate_approval(
                rt,
                user_id=str(ctx_for_user.get("actor_id") or ctx_for_user.get("user_id") or "admin"),
                skill_id=str(skill_id),
                action="execute",
                details=details or f"execute workspace skill {skill_id}",
                metadata={
                    "skill_id": str(skill_id),
                    "action": "execute",
                    "reason": gate.get("reason"),
                    "provenance": (getattr(skill, "metadata", None) or {}).get("provenance") if isinstance(getattr(skill, "metadata", None), dict) else {},
                    "integrity": (getattr(skill, "metadata", None) or {}).get("integrity") if isinstance(getattr(skill, "metadata", None), dict) else {},
                },
            )
            try:
                await _record_changeset(
                    rt,
                    name="skill_signature_gate",
                    target_type="skill",
                    target_id=str(skill_id),
                    status="approval_required",
                    args={"scope": "workspace", "action": "execute", "reason": gate.get("reason")},
                    approval_request_id=rid,
                )
            except Exception:
                pass
            resp = {
                "ok": False,
                "run_id": new_prefixed_id("run"),
                "trace_id": None,
                "status": RunStatus.waiting_approval.value,
                "legacy_status": "approval_required",
                "output": None,
                "error": {"code": "APPROVAL_REQUIRED", "message": "approval_required", "detail": {"approval_request_id": rid, "reason": gate.get("reason")}},
                "approval_request_id": rid,
                "reason": gate.get("reason"),
            }
            try:
                await _audit_execute(rt, http_request=http_request, payload={"context": ctx_for_user}, resource_type="skill", resource_id=str(skill_id), resp=resp, action="execute_skill")
            except Exception:
                pass
            return resp
        if not _is_approval_resolved_approved(rt, approval_request_id):
            try:
                await _record_changeset(
                    rt,
                    name="skill_signature_gate",
                    target_type="skill",
                    target_id=str(skill_id),
                    status="failed",
                    args={"scope": "workspace", "action": "execute", "reason": gate.get("reason")},
                    error="not_approved",
                    approval_request_id=approval_request_id,
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message="not_approved",
                    approval_request_id=str(approval_request_id),
                    next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(approval_request_id)}],
                ),
            )
        try:
            await _record_changeset(rt, name="skill_signature_gate", target_type="skill", target_id=str(skill_id), status="success", args={"scope": "workspace", "action": "execute"}, approval_request_id=approval_request_id)
        except Exception:
            pass

    user_id = str(ctx_for_user.get("actor_id") or ctx_for_user.get("user_id") or "system")
    harness = get_harness()
    exec_req = ExecutionRequest(
        kind="skill",
        target_id=skill_id,
        payload={"input": request.input, "context": ctx_for_user, "mode": getattr(request, "mode", "inline"), "options": getattr(request, "options", None) or None},
        user_id=user_id,
        session_id=str(ctx_for_user.get("session_id") or "default"),
    )
    result = await harness.execute(exec_req)
    resp = wrap_execution_result_as_run_summary(result)
    try:
        await _audit_execute(rt, http_request=http_request, payload={"context": ctx_for_user}, resource_type="skill", resource_id=str(skill_id), resp=resp, action="execute_skill")
    except Exception:
        pass
    return JSONResponse(status_code=200 if resp.get("ok") else int(getattr(result, "http_status", 500) or 500), content=resp)


@router.get("/workspace/skills/{skill_id}/agents")
async def get_workspace_skill_agents(skill_id: str, rt: RuntimeDep = None):
    """Get agents bound to workspace skill."""
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    agent_ids = await mgr.get_bound_agents(skill_id)
    return {"agents": [{"id": a} for a in agent_ids], "total": len(agent_ids)}


@router.get("/workspace/skills/{skill_id}/executions")
async def list_workspace_skill_executions(skill_id: str, limit: int = 100, offset: int = 0, rt: RuntimeDep = None):
    """List workspace skill executions."""
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await mgr.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    store = _store(rt)
    if store:
        items, total = await store.list_skill_executions(skill_id, limit=limit, offset=offset)
        executions = [
            {
                "execution_id": r["id"],
                "skill_id": r["skill_id"],
                "status": r["status"],
                "input": r.get("input"),
                "output": r.get("output"),
                "error": r.get("error"),
                "trace_id": r.get("trace_id"),
                "start_time": datetime.utcfromtimestamp(r["start_time"]).isoformat() if r.get("start_time") else None,
                "end_time": datetime.utcfromtimestamp(r["end_time"]).isoformat() if r.get("end_time") else None,
                "duration_ms": r.get("duration_ms"),
            }
            for r in items
        ]
        return {"executions": executions, "total": total}
    return {"executions": [], "total": 0}


@router.get("/workspace/skills/{skill_id}/versions")
async def get_workspace_skill_versions(skill_id: str, rt: RuntimeDep = None):
    """Get versions for a workspace skill."""
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await mgr.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    registry = get_skill_registry()
    versions = registry.get_versions(skill_id)
    return {"versions": [{"version": v.version, "is_active": v.is_active} for v in versions]}


@router.get("/workspace/skills/{skill_id}/versions/{version}")
async def get_workspace_skill_version(skill_id: str, version: str, rt: RuntimeDep = None):
    """Get specific version config for workspace skill."""
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await mgr.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    registry = get_skill_registry()
    config = registry.get_version(skill_id, version)
    if not config:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")
    try:
        from dataclasses import asdict, is_dataclass

        cfg_dict = asdict(config) if is_dataclass(config) else dict(config)  # type: ignore[arg-type]
    except Exception:
        cfg_dict = {
            "name": getattr(config, "name", ""),
            "description": getattr(config, "description", ""),
            "input_schema": getattr(config, "input_schema", {}) or {},
            "output_schema": getattr(config, "output_schema", {}) or {},
            "timeout": getattr(config, "timeout", None),
            "metadata": getattr(config, "metadata", {}) or {},
        }
    return {"version": version, "config": cfg_dict}


@router.post("/workspace/skills/{skill_id}/versions/{version}/rollback")
async def rollback_workspace_skill_version(skill_id: str, version: str, rt: RuntimeDep = None):
    """Rollback workspace skill to a specific version."""
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await mgr.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    registry = get_skill_registry()
    ok = registry.rollback_version(skill_id, version)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")
    active_version = registry.get_active_version(skill_id) if hasattr(registry, "get_active_version") else version
    return {"status": "rolled_back", "active_version": active_version}


@router.get("/workspace/skills/{skill_id}/active-version")
async def get_workspace_skill_active_version(skill_id: str, rt: RuntimeDep = None):
    """Get currently active version for a workspace skill."""
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await mgr.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    registry = get_skill_registry()
    active_version = registry.get_active_version(skill_id) if hasattr(registry, "get_active_version") else None
    return {"skill_id": skill_id, "active_version": active_version}


@router.get("/workspace/skills/{skill_id}/execution-help")
async def get_workspace_skill_execution_help(skill_id: str, rt: RuntimeDep = None):
    """Get execution input help/examples for a skill."""
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await mgr.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    data = await mgr.get_skill_execution_help(skill_id)  # type: ignore[attr-defined]
    if not data:
        raise HTTPException(status_code=404, detail="Execution help not found")
    return data


@router.get("/workspace/skills/{skill_id}/skill-md")
async def get_workspace_skill_markdown(skill_id: str, rt: RuntimeDep = None):
    """Fetch raw SKILL.md content for a workspace skill (for UI preview)."""
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await mgr.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    try:
        md_path = mgr._find_skill_md(skill_id)  # type: ignore[attr-defined]
        if not md_path:
            raise HTTPException(status_code=404, detail="SKILL.md not found")
        p = Path(str(md_path)).expanduser().resolve()
        if not p.exists():
            raise HTTPException(status_code=404, detail="SKILL.md not found")

        # Security: only allow reading files under workspace skills paths.
        allowed_roots = []
        try:
            for root in mgr._resolve_skills_paths():  # type: ignore[attr-defined]
                allowed_roots.append(Path(str(root)).expanduser().resolve())
        except Exception:
            allowed_roots = []
        if allowed_roots and not any(str(p).startswith(str(r) + "/") or str(p) == str(r) for r in allowed_roots):
            raise HTTPException(status_code=403, detail="SKILL.md path is outside workspace scope")

        text = p.read_text(encoding="utf-8", errors="replace")
        if len(text) > 200_000:
            text = text[:200_000] + "\n\n[TRUNCATED]"
        return {"skill_id": skill_id, "path": str(p), "content": text}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read SKILL.md: {e}")


@router.put("/workspace/skills/{skill_id}/skill-md")
async def update_workspace_skill_markdown(skill_id: str, request: Dict[str, Any], http_request: Request, rt: RuntimeDep = None):
    """
    Update SKILL.md for a workspace skill.

    Supported modes:
    - replace_body: keep frontmatter as-is, replace body (recommended for "开发者精修 SOP")
    - replace_all: overwrite the full file content (advanced; may change frontmatter)
    """
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    deny = await rbac_guard(http_request=http_request, payload=request or {}, action="update", resource_type="skill", resource_id=str(skill_id))
    if deny:
        return deny

    skill = await mgr.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")

    mode = str((request or {}).get("mode") or "replace_body").strip().lower()
    body = (request or {}).get("body")
    content = (request or {}).get("content")

    if mode not in ("replace_body", "replace_all"):
        raise HTTPException(status_code=400, detail="invalid_mode")
    if mode == "replace_body" and not isinstance(body, str):
        raise HTTPException(status_code=400, detail="body_required")
    if mode == "replace_all" and not isinstance(content, str):
        raise HTTPException(status_code=400, detail="content_required")

    try:
        md_path = mgr._find_skill_md(skill_id)  # type: ignore[attr-defined]
        if not md_path:
            raise HTTPException(status_code=404, detail="SKILL.md not found")
        p = Path(str(md_path)).expanduser().resolve()
        if not p.exists():
            raise HTTPException(status_code=404, detail="SKILL.md not found")

        # Security: only allow writing files under workspace skills paths.
        allowed_roots = []
        try:
            for root in mgr._resolve_skills_paths():  # type: ignore[attr-defined]
                allowed_roots.append(Path(str(root)).expanduser().resolve())
        except Exception:
            allowed_roots = []
        if allowed_roots and not any(str(p).startswith(str(r) + "/") or str(p) == str(r) for r in allowed_roots):
            raise HTTPException(status_code=403, detail="SKILL.md path is outside workspace scope")

        raw = p.read_text(encoding="utf-8", errors="replace")
        if mode == "replace_all":
            text = str(content)
        else:
            # Keep frontmatter text as-is; only replace body.
            if raw.startswith("---"):
                end = raw.find("\n---\n", 3)
                if end != -1:
                    header = raw[: end + 5]
                    text = header + "\n" + str(body).lstrip()
                else:
                    # no proper frontmatter end marker; treat as plain markdown
                    text = str(body)
            else:
                text = str(body)

        if len(text) > 500_000:
            raise HTTPException(status_code=400, detail="skill_md_too_large")

        # Snapshot before overwrite (best-effort)
        try:
            skill_dir = p.parent
            rev_dir = skill_dir / ".revisions" / datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            rev_dir.mkdir(parents=True, exist_ok=True)
            rev_dir.joinpath("SKILL.md").write_text(raw, encoding="utf-8")
        except Exception:
            pass

        p.write_text(text, encoding="utf-8")

        # Reload managers so updated SOP/frontmatter is visible to runtime + UI.
        _reload_workspace_managers(rt)

        # Return lint for fast feedback
        lint = None
        try:
            s2 = await mgr.get_skill(skill_id)
            from core.management.skill_linter import lint_skill

            lint = lint_skill(s2 or skill)
        except Exception:
            lint = None

        return {"status": "updated", "skill_id": skill_id, "path": str(p), "lint": lint}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write SKILL.md: {e}")


@router.post("/workspace/skills/{skill_id}/reload")
async def reload_workspace_skill(skill_id: str, rt: RuntimeDep = None):
    """Best-effort reload workspace managers (pull latest SKILL.md edits from disk)."""
    _reload_workspace_managers(rt)
    mgr = _ws_skill_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    s = await mgr.get_skill(skill_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return {"status": "reloaded", "skill_id": skill_id}
