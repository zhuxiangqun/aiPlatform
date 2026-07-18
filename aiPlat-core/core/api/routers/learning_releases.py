from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

from core.api.deps import actor_from_http
from core.api.utils.governance import gate_error_envelope, governance_links, ui_url
from core.governance.changeset import record_changeset
from core.governance.gating import autosmoke_enforce, gate_with_change_control, new_change_id
from core.harness.kernel.runtime import get_kernel_runtime
from core.learning.workspace_target import ensure_workspace_target
import logging


router = APIRouter()


def _rt():
    return get_kernel_runtime()


def _store():
    rt = _rt()
    return getattr(rt, "execution_store", None) if rt else None


def _approval_mgr():
    rt = _rt()
    return getattr(rt, "approval_manager", None) if rt else None


def _managers():
    rt = _rt()
    return {
        "engine_skill_manager": getattr(rt, "skill_manager", None) if rt else None,
        "workspace_skill_manager": getattr(rt, "workspace_skill_manager", None) if rt else None,
        "engine_agent_manager": getattr(rt, "agent_manager", None) if rt else None,
        "workspace_agent_manager": getattr(rt, "workspace_agent_manager", None) if rt else None,
    }


@router.post("/learning/releases/{candidate_id}/rollback", response_model=Dict[str, Any])
async def rollback_release_candidate(candidate_id: str, request: dict, http_request: Request):
    """
    Rollback a release_candidate (status transitions only).
    Supports optional approval gate (learning:rollback_release).
    """
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    from core.learning.manager import LearningManager
    from core.learning.release import require_rollback_approval, is_approved
    from core.harness.infrastructure.approval.manager import ApprovalManager

    mgr = LearningManager(execution_store=store)
    approval_mgr = _approval_mgr() or ApprovalManager(execution_store=store)

    cand = await store.get_learning_artifact(candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="candidate_not_found")
    if cand.get("kind") != "release_candidate":
        raise HTTPException(status_code=400, detail="not_a_release_candidate")

    user_id = (request or {}).get("user_id") or "system"
    actor0 = actor_from_http(http_request, request if isinstance(request, dict) else None)
    change_id = new_change_id()
    require_approval = bool((request or {}).get("require_approval", False))
    approval_request_id = (request or {}).get("approval_request_id")
    reason = (request or {}).get("reason") or ""

    # Gate: ensure involved targets are verified before rollback (when enforcement enabled).
    try:
        targets: list[tuple[str, str]] = []
        if cand.get("target_type") and cand.get("target_id"):
            targets.append((str(cand.get("target_type")), str(cand.get("target_id"))))
        ids = (cand.get("payload") or {}).get("artifact_ids") if isinstance(cand.get("payload"), dict) else []
        if isinstance(ids, list):
            for aid in ids:
                if not isinstance(aid, str) or not aid:
                    continue
                a = await store.get_learning_artifact(aid)
                if isinstance(a, dict) and a.get("target_type") and a.get("target_id"):
                    targets.append((str(a.get("target_type")), str(a.get("target_id"))))
        uniq = list({(t[0].lower(), t[1]) for t in targets})
        if autosmoke_enforce(store=store):
            ms = _managers()
            change_id = await gate_with_change_control(
                store=store,
                operation="learning.release.rollback",
                targets=uniq,
                actor=actor0,
                approval_request_id=str(approval_request_id or "").strip() or None,
                workspace_agent_manager=ms.get("workspace_agent_manager"),
                workspace_skill_manager=ms.get("workspace_skill_manager"),
                skill_manager=ms.get("engine_skill_manager"),
            )
    except HTTPException:
        raise
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    if require_approval:
        if not approval_request_id:
            req_id = await require_rollback_approval(
                approval_manager=approval_mgr,
                user_id=user_id,
                candidate_id=candidate_id,
                regression_report_id=None,
                details=reason or "manual_rollback",
            )
            try:
                await record_changeset(
                    store=store,
                    name="learning.release.rollback",
                    target_type="change",
                    target_id=change_id,
                    status="approval_required",
                    args={"candidate_id": candidate_id, "reason": reason},
                    approval_request_id=req_id,
                    user_id=str(actor0.get("actor_id") or "admin"),
                    tenant_id=str(actor0.get("tenant_id") or "") or None,
                    session_id=str(actor0.get("session_id") or "") or None,
                )
            except Exception as e:
                logging.warning(str(e), exc_info=True)
            return {"status": "approval_required", "approval_request_id": req_id, "change_id": change_id, "links": governance_links(change_id=change_id, approval_request_id=req_id)}
        if not is_approved(approval_mgr, approval_request_id):
            try:
                await record_changeset(
                    store=store,
                    name="learning.release.rollback",
                    target_type="change",
                    target_id=change_id,
                    status="failed",
                    args={"candidate_id": candidate_id, "reason": reason},
                    error="not_approved",
                    approval_request_id=approval_request_id,
                    user_id=str(actor0.get("actor_id") or "admin"),
                    tenant_id=str(actor0.get("tenant_id") or "") or None,
                    session_id=str(actor0.get("session_id") or "") or None,
                )
            except Exception as e:
                logging.warning(str(e), exc_info=True)
            raise HTTPException(  # noqa: error-structured
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message="not_approved",
                    change_id=change_id,
                    approval_request_id=str(approval_request_id),
                    next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(approval_request_id)}],
                ),
            )

    await mgr.set_artifact_status(artifact_id=candidate_id, status="rolled_back", metadata_update={"rolled_back_via": "core_api", "reason": reason, "approval_request_id": approval_request_id})
    ids2 = (cand.get("payload") or {}).get("artifact_ids") if isinstance(cand.get("payload"), dict) else []
    if isinstance(ids2, list):
        for aid in ids2:
            if isinstance(aid, str) and aid:
                await mgr.set_artifact_status(artifact_id=aid, status="rolled_back", metadata_update={"rolled_back_by_candidate": candidate_id})

    # Policy 自进化：回滚时恢复 previous_policy_snapshot（best-effort）。
    try:
        if str(cand.get("target_type") or "").lower() == "policy":
            meta0 = cand.get("metadata") if isinstance(cand.get("metadata"), dict) else {}
            tenant_policy_id = meta0.get("tenant_policy_id") or cand.get("target_id")
            prev = meta0.get("previous_policy_snapshot") if isinstance(meta0.get("previous_policy_snapshot"), dict) else None
            if isinstance(tenant_policy_id, str) and tenant_policy_id and isinstance(prev, dict) and isinstance(prev.get("policy"), dict):
                await store.upsert_tenant_policy(tenant_id=str(tenant_policy_id), policy=prev.get("policy") or {}, version=None)
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # Best-effort: reflect rollback into target skill metadata for runtime gating.
    try:
        if str(cand.get("target_type") or "").lower() == "skill" and cand.get("target_id"):
            ms = _managers()
            sid = str(cand.get("target_id"))
            mgr2 = None
            wsid = sid
            target_skill = None
            if ms.get("workspace_skill_manager"):
                target_skill = await ms["workspace_skill_manager"].get_skill(sid)
                if target_skill:
                    mgr2 = ms["workspace_skill_manager"]
            if not target_skill and ms.get("engine_skill_manager"):
                target_skill = await ms["engine_skill_manager"].get_skill(sid)
                mgr2 = ms["engine_skill_manager"]

            cand_meta = cand.get("metadata") if isinstance(cand.get("metadata"), dict) else {}
            rb_skill_id = cand_meta.get("published_workspace_skill_id") or cand_meta.get("published_skill_id")
            rb_to_ver = cand_meta.get("rollback_to_skill_version")
            if ms.get("workspace_skill_manager") and isinstance(rb_skill_id, str) and rb_skill_id:
                wsid = rb_skill_id
                target_skill = await ms["workspace_skill_manager"].get_skill(wsid)
                mgr2 = ms["workspace_skill_manager"] if target_skill else mgr2
                if mgr2 and isinstance(rb_to_ver, str) and rb_to_ver:
                    try:
                        if hasattr(mgr2, "rollback_version"):
                            await mgr2.rollback_version(wsid, rb_to_ver)  # type: ignore[attr-defined]
                    except Exception as e:
                        logging.warning(str(e), exc_info=True)

            if target_skill and mgr2:
                meta = getattr(target_skill, "metadata", None) if target_skill else None
                gov = meta.get("governance") if isinstance(meta, dict) and isinstance(meta.get("governance"), dict) else {}
                gov2 = dict(gov)
                if gov2.get("published_candidate_id") == candidate_id:
                    gov2.pop("published_candidate_id", None)
                    gov2.pop("published_at", None)
                gov2.update({"status": "rolled_back", "rolled_back_candidate_id": candidate_id})
                await mgr2.update_skill(wsid, metadata={"governance": gov2})
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # PR-10: optionally disable rollout if it points to this candidate (best-effort)
    try:
        tid = actor0.get("tenant_id")
        if tid:
            target_type = str(cand.get("target_type") or "")
            target_id = str(cand.get("target_id") or "")
            rr = await store.get_release_rollout(tenant_id=str(tid), target_type=target_type, target_id=target_id)
            if rr and str(rr.get("candidate_id") or "") == str(candidate_id):
                await store.upsert_release_rollout(
                    tenant_id=str(tid),
                    target_type=target_type,
                    target_id=target_id,
                    candidate_id=str(candidate_id),
                    mode=str(rr.get("mode") or "percentage"),
                    percentage=rr.get("percentage"),
                    include_actor_ids=rr.get("include_actor_ids"),
                    exclude_actor_ids=rr.get("exclude_actor_ids"),
                    enabled=False,
                    metadata={"disabled_via": "rollback_release_candidate"},
                )
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    try:
        await record_changeset(
            store=store,
            name="learning.release.rollback",
            target_type="change",
            target_id=change_id,
            status="success",
            args={"candidate_id": candidate_id, "reason": reason},
            approval_request_id=approval_request_id,
            user_id=str(actor0.get("actor_id") or "admin"),
            tenant_id=str(actor0.get("tenant_id") or "") or None,
            session_id=str(actor0.get("session_id") or "") or None,
        )
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    return {"status": "rolled_back", "candidate_id": candidate_id, "approval_request_id": approval_request_id, "change_id": change_id, "links": governance_links(change_id=change_id, approval_request_id=str(approval_request_id) if approval_request_id else None)}
