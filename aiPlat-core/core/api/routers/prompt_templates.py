from __future__ import annotations

import difflib
import hashlib
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from core.api.deps.rbac import actor_from_http
from core.api.utils.governance import gate_error_envelope, governance_links, ui_url
from core.governance.changeset import record_changeset
from core.harness.kernel.runtime import get_kernel_runtime
from core.schemas import PromptTemplateRollbackRequest, PromptTemplateUpsertRequest

router = APIRouter()


def _rt():
    return get_kernel_runtime()


def _store():
    rt = _rt()
    return getattr(rt, "execution_store", None) if rt else None


def _approval_manager():
    rt = _rt()
    return getattr(rt, "approval_manager", None) if rt else None


def _job_scheduler():
    rt = _rt()
    return getattr(rt, "job_scheduler", None) if rt else None


def _new_change_id() -> str:
    return f"chg-{uuid.uuid4().hex[:12]}"


def _parse_prompt_metadata(tpl: Dict[str, Any]) -> Dict[str, Any]:
    md: Dict[str, Any] = {}
    if isinstance(tpl.get("metadata"), dict):
        md = tpl.get("metadata")  # type: ignore[assignment]
    elif isinstance(tpl.get("metadata_json"), str) and tpl.get("metadata_json"):
        try:
            import json as _json

            md2 = _json.loads(str(tpl.get("metadata_json") or "{}"))
            md = md2 if isinstance(md2, dict) else {}
        except Exception:
            md = {}
    return md if isinstance(md, dict) else {}


def _select_release_version(
    *,
    tpl: Dict[str, Any],
    release: Dict[str, Any],
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Resolve an "effective" prompt template version based on release semantics:
    - pinned_version: always use this version
    - rollout: weighted list [{version, weight}], deterministic bucketing
    """
    current_version = str(tpl.get("version") or "")
    pinned = release.get("pinned_version")
    if isinstance(pinned, str) and pinned.strip():
        return {"version": pinned.strip(), "strategy": "pinned"}

    rollout = release.get("rollout") if isinstance(release.get("rollout"), list) else []
    items: list[dict[str, Any]] = []
    total = 0
    for it in rollout:
        if not isinstance(it, dict):
            continue
        v = str(it.get("version") or "").strip()
        if not v:
            continue
        try:
            w = int(it.get("weight") or 0)
        except Exception:
            w = 0
        if w <= 0:
            continue
        items.append({"version": v, "weight": w})
        total += w
    if total <= 0 or not items:
        return {"version": current_version, "strategy": "current"}

    key = str(session_id or user_id or tenant_id or "default")
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    bucket = int(h[:8], 16) % total
    acc = 0
    for it in items:
        acc += int(it["weight"])
        if bucket < acc:
            return {
                "version": str(it["version"]),
                "strategy": "rollout",
                "bucket": bucket,
                "bucket_total": total,
                "bucket_key": key,
            }
    return {"version": current_version, "strategy": "current"}


def _is_approval_resolved_approved(approval_request_id: str) -> bool:
    mgr = _approval_manager()
    if not approval_request_id or not mgr:
        return False
    from core.harness.infrastructure.approval.types import RequestStatus

    r = mgr.get_request(str(approval_request_id))
    if not r:
        return False
    return r.status in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED)


async def _require_onboarding_approval(*, operation: str, user_id: str, details: str, metadata: Dict[str, Any]) -> str:
    """
    Prompt templates release / write operations are global-impact changes, so by default they go through approvals.
    """
    from core.harness.infrastructure.approval.types import ApprovalContext, ApprovalRule, RuleType

    mgr = _approval_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Approval manager not available")
    rule = ApprovalRule(
        rule_id=f"onboarding_{operation}",
        rule_type=RuleType.SENSITIVE_OPERATION,
        name=f"Onboarding {operation} 审批",
        description=f"{operation} onboarding 需要审批",
        priority=1,
        metadata={"sensitive_operations": [f"onboarding:{operation}"]},
    )
    mgr.register_rule(rule)
    ctx = ApprovalContext(
        user_id=user_id,
        operation=f"onboarding:{operation}",
        operation_context={"details": details},
        metadata=metadata or {},
    )
    req = mgr.create_request(ctx, rule=rule)
    try:
        await mgr._persist(req)  # type: ignore[attr-defined]
    except Exception:
        pass
    return req.request_id


async def _record_changeset(
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
    store = _store()
    return await record_changeset(
        store=store,
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


@router.get("/prompts")
async def list_prompt_templates(limit: int = 100, offset: int = 0):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_prompt_templates(limit=int(limit), offset=int(offset))


@router.get("/prompts/{template_id}")
async def get_prompt_template(template_id: str):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    tpl = await store.get_prompt_template(template_id=str(template_id))
    if not tpl:
        raise HTTPException(status_code=404, detail="not_found")
    return tpl


@router.get("/prompts/{template_id}/resolve")
async def resolve_prompt_template(template_id: str, tenant_id: Optional[str] = None, user_id: Optional[str] = None, session_id: Optional[str] = None):
    """
    Resolve effective prompt version with optional release semantics (P1):
    - pinned_version
    - rollout (weighted bucketing)
    """
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    tpl = await store.get_prompt_template(template_id=str(template_id))
    if not tpl:
        raise HTTPException(status_code=404, detail="not_found")
    md = _parse_prompt_metadata(tpl)
    rel = md.get("release") if isinstance(md.get("release"), dict) else {}
    rel = rel if isinstance(rel, dict) else {}
    sel = _select_release_version(tpl=tpl, release=rel, tenant_id=tenant_id, user_id=user_id, session_id=session_id)
    ver = str(sel.get("version") or tpl.get("version") or "")
    vrow = None
    try:
        vrow = await store.get_prompt_template_version(template_id=str(template_id), version=str(ver))
    except Exception:
        vrow = None
    out = dict(tpl)
    if isinstance(vrow, dict) and vrow.get("template"):
        out["template"] = vrow.get("template")
        out["version"] = str(ver)
        out["metadata_json"] = vrow.get("metadata_json")
    out["release"] = rel
    out["resolution"] = sel
    return out


@router.post("/prompts/{template_id}/release")
async def set_prompt_template_release(template_id: str, request: dict, http_request: Request):
    """
    P1: Prompt 发布/灰度语义（不修改 template 内容/版本，只修改 metadata.release）。
    Supports:
      - pinned_version: string | null
      - rollout: [{version, weight}] | []
      - require_approval/approval_request_id/details
    """
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    tpl = await store.get_prompt_template(template_id=str(template_id))
    if not tpl:
        raise HTTPException(status_code=404, detail="not_found")

    change_id = _new_change_id()
    md = _parse_prompt_metadata(tpl)
    ver_md = md.get("verification") if isinstance(md.get("verification"), dict) else {}
    st = str(ver_md.get("status") or "").strip().lower()
    # Require verified before altering release settings (conservative).
    if st and st not in {"verified", "passed", "success"}:
        raise HTTPException(
            status_code=409,
            detail=gate_error_envelope(
                code="autosmoke_not_verified",
                message=f"autosmoke_not_verified: current_verification_status={st}",
                change_id=change_id,
                next_actions=[
                    {"type": "open_change_control", "label": "打开变更控制台", "url": ui_url(f"/diagnostics/change-control/{change_id}")},
                    {"type": "open_prompts", "label": "打开 Prompt 模板", "url": ui_url("/core/prompts")},
                    {"type": "open_doctor", "label": "打开 Doctor", "url": ui_url("/diagnostics/doctor")},
                ],
                detail={"template_id": str(template_id), "verification_status": st},
            ),
        )

    pinned_version = request.get("pinned_version")
    if pinned_version is not None and not (isinstance(pinned_version, str) and pinned_version.strip()):
        pinned_version = None
    pinned_version = str(pinned_version).strip() if isinstance(pinned_version, str) and pinned_version.strip() else None

    rollout = request.get("rollout") if isinstance(request.get("rollout"), list) else []
    norm_rollout = []
    total = 0
    seen = set()
    for it in rollout:
        if not isinstance(it, dict):
            continue
        v = str(it.get("version") or "").strip()
        if not v or v in seen:
            continue
        try:
            w = int(it.get("weight") or 0)
        except Exception:
            w = 0
        if w <= 0:
            continue
        seen.add(v)
        total += w
        norm_rollout.append({"version": v, "weight": w})
    if total > 10000:
        raise HTTPException(status_code=400, detail="invalid_rollout_total")

    # Validate referenced versions exist (best-effort).
    try:
        versions = await store.list_prompt_template_versions(template_id=str(template_id), limit=500, offset=0)
        exist = {str(x.get("version")) for x in (versions.get("items") or []) if isinstance(x, dict) and x.get("version")}
        if pinned_version and pinned_version not in exist:
            raise HTTPException(status_code=400, detail="pinned_version_not_found")
        for it in norm_rollout:
            if it["version"] not in exist:
                raise HTTPException(status_code=400, detail="rollout_version_not_found")
    except HTTPException:
        raise
    except Exception:
        pass

    require_approval = bool(request.get("require_approval", True))
    approval_request_id = request.get("approval_request_id")
    details = str(request.get("details") or f"set prompt template release {template_id}").strip()
    if require_approval:
        if not approval_request_id:
            rid = await _require_onboarding_approval(
                operation="prompt_template_release",
                user_id="admin",
                details=details,
                metadata={"template_id": str(template_id), "pinned_version": pinned_version, "rollout": norm_rollout},
            )
            try:
                await _record_changeset(
                    name="prompt_template_release",
                    target_type="change",
                    target_id=str(change_id),
                    status="approval_required",
                    args={"template_id": str(template_id), "pinned_version": pinned_version, "rollout": norm_rollout},
                    approval_request_id=rid,
                )
            except Exception:
                pass
            return {"status": "approval_required", "approval_request_id": rid, "change_id": change_id, "links": governance_links(change_id=change_id, approval_request_id=rid)}
        if not _is_approval_resolved_approved(str(approval_request_id)):
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message="not_approved",
                    change_id=change_id,
                    approval_request_id=str(approval_request_id),
                    next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(approval_request_id)}],
                ),
            )

    prev_release = md.get("release") if isinstance(md.get("release"), dict) else {}
    prev_release = prev_release if isinstance(prev_release, dict) else {}
    now = time.time()
    actor = actor_from_http(http_request, None)
    new_release = {
        "pinned_version": pinned_version,
        "rollout": norm_rollout,
        "updated_at": now,
        "updated_by": actor.get("actor_id"),
        "previous_release": prev_release,
    }
    await store.update_prompt_template_metadata(template_id=str(template_id), patch={"release": new_release}, merge=True)
    try:
        await _record_changeset(
            name="prompt_template_release",
            target_type="change",
            target_id=str(change_id),
            status="success",
            args={"template_id": str(template_id), "pinned_version": pinned_version, "rollout": norm_rollout},
            result={"updated_at": now},
            approval_request_id=str(approval_request_id) if approval_request_id else None,
        )
    except Exception:
        pass
    return {"status": "updated", "change_id": change_id, "release": new_release, "links": governance_links(change_id=change_id)}


@router.post("/prompts/{template_id}/release/rollback")
async def rollback_prompt_template_release(template_id: str, request: dict, http_request: Request):
    """Rollback metadata.release to previous_release (best-effort)."""
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    tpl = await store.get_prompt_template(template_id=str(template_id))
    if not tpl:
        raise HTTPException(status_code=404, detail="not_found")
    md = _parse_prompt_metadata(tpl)
    cur = md.get("release") if isinstance(md.get("release"), dict) else {}
    cur = cur if isinstance(cur, dict) else {}
    prev = cur.get("previous_release") if isinstance(cur.get("previous_release"), dict) else None
    if not isinstance(prev, dict):
        raise HTTPException(status_code=409, detail="no_previous_release")

    change_id = _new_change_id()
    require_approval = bool((request or {}).get("require_approval", True))
    approval_request_id = (request or {}).get("approval_request_id")
    details = str((request or {}).get("details") or f"rollback prompt template release {template_id}").strip()
    if require_approval:
        if not approval_request_id:
            rid = await _require_onboarding_approval(
                operation="prompt_template_release_rollback",
                user_id="admin",
                details=details,
                metadata={"template_id": str(template_id)},
            )
            return {"status": "approval_required", "approval_request_id": rid, "change_id": change_id, "links": governance_links(change_id=change_id, approval_request_id=rid)}
        if not _is_approval_resolved_approved(str(approval_request_id)):
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message="not_approved",
                    change_id=change_id,
                    approval_request_id=str(approval_request_id),
                    next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(approval_request_id)}],
                ),
            )

    now = time.time()
    actor = actor_from_http(http_request, None)
    prev2 = dict(prev)
    prev2["updated_at"] = now
    prev2["updated_by"] = actor.get("actor_id")
    prev2["previous_release"] = cur
    await store.update_prompt_template_metadata(template_id=str(template_id), patch={"release": prev2}, merge=True)
    try:
        await _record_changeset(
            name="prompt_template_release_rollback",
            target_type="change",
            target_id=str(change_id),
            status="success",
            args={"template_id": str(template_id)},
            result={"updated_at": now},
            approval_request_id=str(approval_request_id) if approval_request_id else None,
        )
    except Exception:
        pass
    return {"status": "rolled_back", "change_id": change_id, "release": prev2, "links": governance_links(change_id=change_id)}


@router.post("/prompts")
async def upsert_prompt_template(request: PromptTemplateUpsertRequest, http_request: Request):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    # Autosmoke gate strategy (machine-picked):
    # - When verification is pending/failed, block *new upserts* (avoid piling changes).
    # - Rollback remains available as recovery path.
    change_id = _new_change_id()

    prev = None
    try:
        prev = await store.get_prompt_template(template_id=str(request.template_id))
    except Exception:
        prev = None

    # Gate: block new upserts when last verification isn't verified.
    try:
        if isinstance(prev, dict):
            md = _parse_prompt_metadata(prev)
            ver = md.get("verification") if isinstance(md.get("verification"), dict) else {}
            st = str(ver.get("status") or "").strip().lower()
            if st in {"pending", "failed"}:
                # Record change attempt for auditing (best-effort).
                try:
                    await _record_changeset(
                        name="prompt_template_upsert",
                        target_type="change",
                        target_id=str(change_id),
                        status="failed",
                        args={"operation": "prompt_template_upsert", "template_id": request.template_id, "name": request.name},
                        error="autosmoke_not_verified",
                        approval_request_id=request.approval_request_id,
                    )
                except Exception:
                    pass
                raise HTTPException(
                    status_code=409,
                    detail=gate_error_envelope(
                        code="autosmoke_not_verified",
                        message=f"autosmoke_not_verified: current_verification_status={st}",
                        change_id=change_id,
                        approval_request_id=str(request.approval_request_id) if request.approval_request_id else None,
                        next_actions=[
                            {"type": "open_change_control", "label": "打开变更控制台", "url": ui_url(f"/diagnostics/change-control/{change_id}")},
                            {"type": "open_prompts", "label": "打开 Prompt 模板", "url": ui_url("/core/prompts")},
                            {"type": "open_doctor", "label": "打开 Doctor", "url": ui_url("/diagnostics/doctor")},
                        ],
                        detail={"template_id": str(request.template_id), "verification_status": st},
                    ),
                )
    except HTTPException:
        raise
    except Exception:
        # Fail-open: do not block prompt ops on metadata parsing errors.
        pass

    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_onboarding_approval(
                operation="prompt_template_upsert",
                user_id="admin",
                details=request.details or f"upsert prompt template {request.template_id}",
                metadata={"template_id": request.template_id, "name": request.name},
            )
            try:
                await _record_changeset(
                    name="prompt_template_upsert",
                    target_type="change",
                    target_id=str(change_id),
                    status="approval_required",
                    args={"operation": "prompt_template_upsert", "template_id": request.template_id, "name": request.name},
                    approval_request_id=rid,
                )
            except Exception:
                pass
            return {
                "status": "approval_required",
                "approval_request_id": rid,
                "change_id": change_id,
                "links": governance_links(change_id=change_id, approval_request_id=rid),
            }
        if not _is_approval_resolved_approved(str(request.approval_request_id)):
            try:
                await _record_changeset(
                    name="prompt_template_upsert",
                    target_type="change",
                    target_id=str(change_id),
                    status="failed",
                    args={"operation": "prompt_template_upsert", "template_id": request.template_id, "name": request.name},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message="not_approved",
                    change_id=change_id,
                    approval_request_id=str(request.approval_request_id),
                    next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(request.approval_request_id)}],
                ),
            )

    try:
        res = await store.upsert_prompt_template(
            template_id=request.template_id,
            name=request.name,
            template=request.template,
            metadata=request.metadata or {},
            increment_version=bool(request.increment_version),
        )
    except Exception as e:
        try:
            await _record_changeset(
                name="prompt_template_upsert",
                target_type="change",
                target_id=str(change_id),
                status="failed",
                args={"operation": "prompt_template_upsert", "template_id": request.template_id, "name": request.name},
                error=f"exception:{type(e).__name__}",
                approval_request_id=request.approval_request_id,
            )
        except Exception:
            pass
        raise

    # Audit as a "changeset" syscall event (no secret content, hash only)
    try:
        await _record_changeset(
            name="prompt_template_upsert",
            target_type="change",
            target_id=str(change_id),
            status="success",
            args={
                "operation": "prompt_template_upsert",
                "template_id": request.template_id,
                "name": request.name,
                "prev_version": (prev or {}).get("version") if isinstance(prev, dict) else None,
            },
            result={
                "version": res.get("version") if isinstance(res, dict) else None,
                "template_sha256": hashlib.sha256(str(request.template).encode("utf-8")).hexdigest(),
                "template_len": len(str(request.template)),
                "verification_status": "pending",
            },
            approval_request_id=request.approval_request_id,
        )
    except Exception:
        pass

    # Verification: mark pending + enqueue autosmoke (best-effort)
    try:
        js = _job_scheduler()
        if js is not None:
            from core.harness.smoke import enqueue_autosmoke

            await store.update_prompt_template_metadata(
                template_id=str(request.template_id),
                patch={"verification": {"status": "pending", "updated_at": time.time(), "source": "autosmoke"}, "governance": {"latest_change_id": change_id}},
                merge=True,
            )

            tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
            actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")

            async def _on_complete(job_run: Dict[str, Any]):
                st = str(job_run.get("status") or "")
                ver = {
                    "status": "verified" if st == "completed" else "failed",
                    "updated_at": time.time(),
                    "source": "autosmoke",
                    "job_id": str(job_run.get("job_id") or ""),
                    "job_run_id": str(job_run.get("id") or ""),
                    "trace_id": str(job_run.get("trace_id") or "") or None,
                    "reason": str(job_run.get("error") or ""),
                }
                try:
                    await store.update_prompt_template_metadata(template_id=str(request.template_id), patch={"verification": ver}, merge=True)
                except Exception:
                    pass

                # Change Control writeback (best-effort): record autosmoke result to same change_id.
                try:
                    await _record_changeset(
                        name="prompt_template_autosmoke",
                        target_type="change",
                        target_id=str(change_id),
                        status="success" if st == "completed" else "failed",
                        args={"operation": "prompt_template_autosmoke", "template_id": str(request.template_id)},
                        result={"verification": ver, "job": {"job_id": ver.get("job_id"), "job_run_id": ver.get("job_run_id")}},
                        trace_id=ver.get("trace_id"),
                        run_id=str(job_run.get("run_id") or job_run.get("id") or "") or None,
                        approval_request_id=request.approval_request_id,
                        tenant_id=http_request.headers.get("X-AIPLAT-TENANT-ID", None),
                    )
                except Exception:
                    pass

            await enqueue_autosmoke(
                execution_store=store,
                job_scheduler=js,
                resource_type="prompt_template",
                resource_id=str(request.template_id),
                tenant_id=tenant_id or "ops_smoke",
                actor_id=actor_id or "admin",
                detail={"op": "prompt_template_upsert", "template_id": str(request.template_id), "change_id": str(change_id)},
                on_complete=_on_complete,
            )
    except Exception:
        pass
    return {
        "status": "updated",
        "template": res,
        "change_id": change_id,
        "approval_request_id": request.approval_request_id,
        "links": governance_links(change_id=change_id, approval_request_id=str(request.approval_request_id) if request.approval_request_id else None),
    }


@router.post("/prompts/{template_id}/rollback")
async def rollback_prompt_template(template_id: str, request: PromptTemplateRollbackRequest, http_request: Request):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    change_id = _new_change_id()

    if request.template_id and str(request.template_id) != str(template_id):
        raise HTTPException(status_code=400, detail="template_id_mismatch")

    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_onboarding_approval(
                operation="prompt_template_rollback",
                user_id="admin",
                details=request.details or f"rollback prompt template {template_id} to {request.version}",
                metadata={"template_id": str(template_id), "version": str(request.version)},
            )
            try:
                await _record_changeset(
                    name="prompt_template_rollback",
                    target_type="change",
                    target_id=str(change_id),
                    status="approval_required",
                    args={"operation": "prompt_template_rollback", "template_id": str(template_id), "version": str(request.version)},
                    approval_request_id=rid,
                )
            except Exception:
                pass
            return {
                "status": "approval_required",
                "approval_request_id": rid,
                "change_id": change_id,
                "links": governance_links(change_id=change_id, approval_request_id=rid),
            }
        if not _is_approval_resolved_approved(str(request.approval_request_id)):
            try:
                await _record_changeset(
                    name="prompt_template_rollback",
                    target_type="change",
                    target_id=str(change_id),
                    status="failed",
                    args={"operation": "prompt_template_rollback", "template_id": str(template_id), "version": str(request.version)},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message="not_approved",
                    change_id=change_id,
                    approval_request_id=str(request.approval_request_id),
                    next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(request.approval_request_id)}],
                ),
            )

    try:
        tpl = await store.rollback_prompt_template_version(template_id=str(template_id), version=str(request.version))
    except KeyError:
        try:
            await _record_changeset(
                name="prompt_template_rollback",
                target_type="change",
                target_id=str(change_id),
                status="failed",
                args={"operation": "prompt_template_rollback", "template_id": str(template_id), "version": str(request.version)},
                error="version_not_found",
                approval_request_id=request.approval_request_id,
            )
        except Exception:
            pass
        raise HTTPException(status_code=404, detail="version_not_found")
    except Exception as e:
        try:
            await _record_changeset(
                name="prompt_template_rollback",
                target_type="change",
                target_id=str(change_id),
                status="failed",
                args={"operation": "prompt_template_rollback", "template_id": str(template_id), "version": str(request.version)},
                error=f"exception:{type(e).__name__}",
                approval_request_id=request.approval_request_id,
            )
        except Exception:
            pass
        raise

    try:
        await _record_changeset(
            name="prompt_template_rollback",
            target_type="change",
            target_id=str(change_id),
            status="success",
            args={"operation": "prompt_template_rollback", "template_id": str(template_id), "version": str(request.version)},
            result={"status": "rolled_back", "verification_status": "pending"},
            approval_request_id=request.approval_request_id,
        )
    except Exception:
        pass

    # Verification: mark pending + enqueue autosmoke (best-effort)
    try:
        js = _job_scheduler()
        if js is not None:
            from core.harness.smoke import enqueue_autosmoke

            await store.update_prompt_template_metadata(
                template_id=str(template_id),
                patch={"verification": {"status": "pending", "updated_at": time.time(), "source": "autosmoke"}, "governance": {"latest_change_id": change_id}},
                merge=True,
            )
            tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
            actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")

            async def _on_complete(job_run: Dict[str, Any]):
                st = str(job_run.get("status") or "")
                ver = {
                    "status": "verified" if st == "completed" else "failed",
                    "updated_at": time.time(),
                    "source": "autosmoke",
                    "job_id": str(job_run.get("job_id") or ""),
                    "job_run_id": str(job_run.get("id") or ""),
                    "trace_id": str(job_run.get("trace_id") or "") or None,
                    "reason": str(job_run.get("error") or ""),
                }
                try:
                    await store.update_prompt_template_metadata(template_id=str(template_id), patch={"verification": ver}, merge=True)
                except Exception:
                    pass

                # Change Control writeback (best-effort): record autosmoke result to same change_id.
                try:
                    await _record_changeset(
                        name="prompt_template_autosmoke",
                        target_type="change",
                        target_id=str(change_id),
                        status="success" if st == "completed" else "failed",
                        args={"operation": "prompt_template_autosmoke", "template_id": str(template_id)},
                        result={"verification": ver, "job": {"job_id": ver.get("job_id"), "job_run_id": ver.get("job_run_id")}},
                        trace_id=ver.get("trace_id"),
                        run_id=str(job_run.get("run_id") or job_run.get("id") or "") or None,
                        approval_request_id=request.approval_request_id,
                        tenant_id=http_request.headers.get("X-AIPLAT-TENANT-ID", None),
                    )
                except Exception:
                    pass

            await enqueue_autosmoke(
                execution_store=store,
                job_scheduler=js,
                resource_type="prompt_template",
                resource_id=str(template_id),
                tenant_id=tenant_id or "ops_smoke",
                actor_id=actor_id or "admin",
                detail={"op": "prompt_template_rollback", "template_id": str(template_id), "version": str(request.version), "change_id": str(change_id)},
                on_complete=_on_complete,
            )
    except Exception:
        pass
    return {
        "status": "rolled_back",
        "template": tpl,
        "change_id": change_id,
        "approval_request_id": request.approval_request_id,
        "links": governance_links(change_id=change_id, approval_request_id=str(request.approval_request_id) if request.approval_request_id else None),
    }


@router.get("/prompts/{template_id}/versions")
async def list_prompt_template_versions(template_id: str, limit: int = 100, offset: int = 0):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_prompt_template_versions(template_id=str(template_id), limit=int(limit), offset=int(offset))


@router.get("/prompts/{template_id}/diff")
async def diff_prompt_template(template_id: str, from_version: Optional[str] = None, to_version: Optional[str] = None):
    """
    Diff prompt template content between two versions.
    Defaults:
      - to_version: current version
      - from_version: previous version (if exists)
    """
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    cur = await store.get_prompt_template(template_id=str(template_id))
    if not cur:
        raise HTTPException(status_code=404, detail="not_found")
    cur_ver = str(cur.get("version") or "")
    cur_tpl = str(cur.get("template") or "")

    # Resolve to_version
    resolved_to_ver = str(to_version) if to_version else cur_ver
    if resolved_to_ver == cur_ver:
        to_tpl = cur_tpl
    else:
        v = await store.get_prompt_template_version(template_id=str(template_id), version=str(resolved_to_ver))
        if not v:
            raise HTTPException(status_code=404, detail="to_version_not_found")
        to_tpl = str(v.get("template") or "")

    # Resolve from_version
    resolved_from_ver = str(from_version) if from_version else ""
    if not resolved_from_ver:
        # previous version: first version in list that is not resolved_to_ver
        vers = await store.list_prompt_template_versions(template_id=str(template_id), limit=20, offset=0)
        for it in (vers.get("items") or []):
            vv = str((it or {}).get("version") or "")
            if vv and vv != resolved_to_ver:
                resolved_from_ver = vv
                break
    if not resolved_from_ver:
        resolved_from_ver = resolved_to_ver
    if resolved_from_ver == cur_ver:
        from_tpl = cur_tpl
    else:
        v2 = await store.get_prompt_template_version(template_id=str(template_id), version=str(resolved_from_ver))
        if not v2:
            raise HTTPException(status_code=404, detail="from_version_not_found")
        from_tpl = str(v2.get("template") or "")

    diff_lines = list(
        difflib.unified_diff(
            from_tpl.splitlines(),
            to_tpl.splitlines(),
            fromfile=f"{template_id}@{resolved_from_ver}",
            tofile=f"{template_id}@{resolved_to_ver}",
            lineterm="",
        )
    )
    diff_text = "\n".join(diff_lines)

    return {
        "status": "ok",
        "template_id": str(template_id),
        "from_version": resolved_from_ver,
        "to_version": resolved_to_ver,
        "from_sha256": hashlib.sha256(from_tpl.encode("utf-8")).hexdigest(),
        "to_sha256": hashlib.sha256(to_tpl.encode("utf-8")).hexdigest(),
        "diff_sha256": hashlib.sha256(diff_text.encode("utf-8")).hexdigest(),
        "diff": diff_text,
        "diff_len": len(diff_text),
    }


@router.delete("/prompts/{template_id}")
async def delete_prompt_template(
    template_id: str,
    http_request: Request,
    require_approval: bool = True,
    approval_request_id: Optional[str] = None,
    details: Optional[str] = None,
):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    change_id = _new_change_id()

    if require_approval:
        if not approval_request_id:
            rid = await _require_onboarding_approval(
                operation="prompt_template_delete",
                user_id="admin",
                details=details or f"delete prompt template {template_id}",
                metadata={"template_id": str(template_id)},
            )
            try:
                await _record_changeset(
                    name="prompt_template_delete",
                    target_type="change",
                    target_id=str(change_id),
                    status="approval_required",
                    args={"operation": "prompt_template_delete", "template_id": str(template_id)},
                    approval_request_id=rid,
                )
            except Exception:
                pass
            return {
                "status": "approval_required",
                "approval_request_id": rid,
                "change_id": change_id,
                "links": governance_links(change_id=change_id, approval_request_id=rid),
            }
        if not _is_approval_resolved_approved(str(approval_request_id)):
            try:
                await _record_changeset(
                    name="prompt_template_delete",
                    target_type="change",
                    target_id=str(change_id),
                    status="failed",
                    args={"operation": "prompt_template_delete", "template_id": str(template_id)},
                    error="not_approved",
                    approval_request_id=str(approval_request_id),
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message="not_approved",
                    change_id=change_id,
                    approval_request_id=str(approval_request_id),
                    next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(approval_request_id)}],
                ),
            )

    ok = await store.delete_prompt_template(template_id=str(template_id))
    try:
        await _record_changeset(
            name="prompt_template_delete",
            target_type="change",
            target_id=str(change_id),
            args={"operation": "prompt_template_delete", "template_id": str(template_id)},
            result={"status": "deleted" if ok else "not_found"},
            approval_request_id=str(approval_request_id) if approval_request_id else None,
        )
    except Exception:
        pass

    # Verification: enqueue autosmoke (best-effort)
    try:
        js = _job_scheduler()
        if ok and js is not None:
            from core.harness.smoke import enqueue_autosmoke

            tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
            actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")

            await enqueue_autosmoke(
                execution_store=store,
                job_scheduler=js,
                resource_type="prompt_template",
                resource_id=str(template_id),
                tenant_id=tenant_id or "ops_smoke",
                actor_id=actor_id or "admin",
                detail={"op": "prompt_template_delete", "template_id": str(template_id), "change_id": str(change_id)},
            )
    except Exception:
        pass
    return {
        "status": "deleted" if ok else "not_found",
        "change_id": change_id,
        "approval_request_id": approval_request_id,
        "links": governance_links(change_id=change_id, approval_request_id=str(approval_request_id) if approval_request_id else None),
    }

