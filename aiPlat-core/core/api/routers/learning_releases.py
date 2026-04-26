from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

from core.api.deps.rbac import actor_from_http
from core.api.utils.governance import gate_error_envelope, governance_links, ui_url
from core.governance.changeset import record_changeset
from core.governance.gating import autosmoke_enforce, gate_with_change_control, new_change_id
from core.harness.kernel.runtime import get_kernel_runtime
from core.learning.workspace_target import ensure_workspace_target


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


@router.post("/learning/releases/{candidate_id}/publish")
async def publish_release_candidate(candidate_id: str, request: dict, http_request: Request):
    """
    Publish a release_candidate (status transitions only).
    Supports optional approval gate using existing ApprovalManager.
    """
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    from core.learning.manager import LearningManager
    from core.learning.release import require_publish_approval, is_approved
    from core.harness.infrastructure.approval.manager import ApprovalManager

    mgr = LearningManager(execution_store=store)
    approval_mgr = _approval_mgr() or ApprovalManager(execution_store=store)

    cand = await store.get_learning_artifact(candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="candidate_not_found")
    if cand.get("kind") != "release_candidate":
        raise HTTPException(status_code=400, detail="not_a_release_candidate")

    actor0 = actor_from_http(http_request, request if isinstance(request, dict) else None)
    change_id = new_change_id()

    # Gate: ensure involved targets are verified before publish (when enforcement enabled).
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
                operation="learning.release.publish",
                targets=uniq,
                actor=actor0,
                approval_request_id=str((request or {}).get("approval_request_id") or "").strip() or None,
                workspace_agent_manager=ms.get("workspace_agent_manager"),
                workspace_skill_manager=ms.get("workspace_skill_manager"),
                skill_manager=ms.get("engine_skill_manager"),
            )
    except HTTPException:
        raise
    except Exception:
        pass

    user_id = (request or {}).get("user_id") or "system"
    tenant_id = actor0.get("tenant_id")
    require_approval = bool((request or {}).get("require_approval", False))
    approval_request_id = (request or {}).get("approval_request_id")
    details = (request or {}).get("details") or ""

    # Canary block gate (hard): canary:block_release_candidate is an approval to *block*.
    try:
        md0 = cand.get("metadata") if isinstance(cand.get("metadata"), dict) else {}
        if bool(md0.get("blocked")) and str(md0.get("blocked_via") or "") == "canary":
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="canary_blocked",
                    message="blocked_by_canary",
                    approval_request_id=str(md0.get("blocked_approval_request_id") or ""),
                    next_actions=[
                        {"type": "open_change_control", "label": "打开 Change Control", "url": ui_url("/diagnostics/change-control")},
                        {"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals")},
                    ],
                ),
            )
        res = await store.list_approval_requests(
            tenant_id=str(tenant_id) if tenant_id is not None else None,
            operation="canary:block_release_candidate",
            limit=2000,
            offset=0,
        )
        items = (res or {}).get("items") if isinstance(res, dict) else None
        if isinstance(items, list):
            for it in items:
                if not isinstance(it, dict):
                    continue
                if str(it.get("status") or "").lower() not in {"pending", "approved", "auto_approved"}:
                    continue
                meta = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
                if str(meta.get("candidate_id") or "") == str(candidate_id):
                    raise HTTPException(
                        status_code=409,
                        detail=gate_error_envelope(
                            code="canary_blocked",
                            message="blocked_by_canary",
                            approval_request_id=str(it.get("request_id") or ""),
                            next_actions=[
                                {"type": "open_change_control", "label": "打开 Change Control", "url": ui_url("/diagnostics/change-control")},
                                {"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(it.get("request_id") or "")},
                            ],
                        ),
                    )
    except HTTPException:
        raise
    except Exception:
        pass

    # Policy 自进化：强制审批（高风险变更不允许 bypass）
    if str(cand.get("target_type") or "").lower() == "policy":
        require_approval = True

    if require_approval:
        if not approval_request_id:
            req_id = await require_publish_approval(
                approval_manager=approval_mgr,
                user_id=user_id,
                candidate_id=candidate_id,
                details=details,
            )
            try:
                await record_changeset(
                    store=store,
                    name="learning.release.publish",
                    target_type="change",
                    target_id=change_id,
                    status="approval_required",
                    args={"candidate_id": candidate_id},
                    approval_request_id=req_id,
                    user_id=str(actor0.get("actor_id") or "admin"),
                    tenant_id=str(actor0.get("tenant_id") or "") or None,
                    session_id=str(actor0.get("session_id") or "") or None,
                )
            except Exception:
                pass
            return {
                "status": "approval_required",
                "approval_request_id": req_id,
                "change_id": change_id,
                "links": governance_links(change_id=change_id, approval_request_id=req_id),
            }
        if not is_approved(approval_mgr, approval_request_id):
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message="not_approved",
                    approval_request_id=str(approval_request_id),
                    next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(approval_request_id)}],
                ),
            )

    now = time.time()
    meta_update = {"published_via": "core_api", "approval_request_id": approval_request_id, "published_at": now}
    expires_at = (request or {}).get("expires_at")
    ttl_seconds = (request or {}).get("ttl_seconds")
    if expires_at is not None:
        try:
            meta_update["expires_at"] = float(expires_at)
        except Exception:
            pass
    if ttl_seconds is not None:
        try:
            ttl = float(ttl_seconds)
            meta_update["ttl_seconds"] = ttl
            if "expires_at" not in meta_update:
                meta_update["expires_at"] = now + ttl
        except Exception:
            pass

    await mgr.set_artifact_status(artifact_id=candidate_id, status="published", metadata_update=meta_update)
    ids = (cand.get("payload") or {}).get("artifact_ids") if isinstance(cand.get("payload"), dict) else []
    if isinstance(ids, list):
        for aid in ids:
            if isinstance(aid, str) and aid:
                await mgr.set_artifact_status(artifact_id=aid, status="published", metadata_update={"published_by_candidate": candidate_id})

    # Policy 自进化：发布时将 policy_revision 应用为 tenant policy 新版本（best-effort）。
    try:
        if str(cand.get("target_type") or "").lower() == "policy" and cand.get("target_id"):
            tenant_policy_id = str(cand.get("target_id"))
            cur = await store.get_tenant_policy(tenant_id=tenant_policy_id)
            cur_policy = cur.get("policy") if isinstance(cur, dict) and isinstance(cur.get("policy"), dict) else {}
            cur_ver = cur.get("version") if isinstance(cur, dict) else None

            def _deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
                out = dict(a or {})
                for k, v in (b or {}).items():
                    if isinstance(v, dict) and isinstance(out.get(k), dict):
                        out[k] = _deep_merge(out.get(k) or {}, v)
                    else:
                        out[k] = v
                return out

            next_policy: Dict[str, Any] = dict(cur_policy or {})
            ids0 = (cand.get("payload") or {}).get("artifact_ids") if isinstance(cand.get("payload"), dict) else []
            if isinstance(ids0, list):
                for aid in ids0:
                    if not isinstance(aid, str) or not aid:
                        continue
                    a = await store.get_learning_artifact(aid)
                    if not isinstance(a, dict) or str(a.get("kind") or "") != "policy_revision" or str(a.get("status") or "") != "published":
                        continue
                    p0 = a.get("payload") if isinstance(a.get("payload"), dict) else {}
                    if isinstance(p0.get("policy"), dict):
                        next_policy = dict(p0.get("policy") or {})
                    elif isinstance(p0.get("patch"), dict):
                        next_policy = _deep_merge(next_policy, p0.get("patch") or {})
                    else:
                        next_policy = _deep_merge(next_policy, p0)

            up = await store.upsert_tenant_policy(
                tenant_id=tenant_policy_id,
                policy=next_policy,
                version=int(cur_ver) if cur_ver is not None else None,
            )
            try:
                await mgr.set_artifact_status(
                    artifact_id=candidate_id,
                    status="published",
                    metadata_update={"tenant_policy_id": tenant_policy_id, "applied_policy_version": up.get("version"), "previous_policy_snapshot": {"version": cur_ver, "policy": cur_policy}},
                )
            except Exception:
                pass
    except Exception:
        pass

    # Best-effort: reflect publish into target skill metadata for runtime gating.
    try:
        if str(cand.get("target_type") or "").lower() == "skill" and cand.get("target_id"):
            ms = _managers()
            sid = str(cand.get("target_id"))
            wsid = sid
            target_skill = None
            mgr2 = None
            if ms.get("workspace_skill_manager"):
                try:
                    target_skill = await ms["workspace_skill_manager"].get_skill(sid)
                    if target_skill:
                        mgr2 = ms["workspace_skill_manager"]
                except Exception:
                    target_skill = None
            if not target_skill and ms.get("workspace_skill_manager"):
                try:
                    ensured = await ensure_workspace_target(
                        target_type="skill",
                        target_id=sid,
                        http_request=http_request,
                        engine_skill_manager=ms.get("engine_skill_manager"),
                        workspace_skill_manager=ms.get("workspace_skill_manager"),
                        engine_agent_manager=ms.get("engine_agent_manager"),
                        workspace_agent_manager=ms.get("workspace_agent_manager"),
                        store=store,
                    )
                    wsid = str(ensured.get("target_id") or sid)
                    target_skill = await ms["workspace_skill_manager"].get_skill(wsid)
                    mgr2 = ms["workspace_skill_manager"] if target_skill else None
                except Exception:
                    pass
            if not target_skill and ms.get("engine_skill_manager"):
                target_skill = await ms["engine_skill_manager"].get_skill(sid)
                mgr2 = ms["engine_skill_manager"]

            if target_skill and mgr2:
                old_version = getattr(target_skill, "version", None)
                ids2 = (cand.get("payload") or {}).get("artifact_ids") if isinstance(cand.get("payload"), dict) else []
                changes_lines = [f"learning release {candidate_id}"]
                try:
                    summ = (cand.get("payload") or {}).get("summary") if isinstance(cand.get("payload"), dict) else ""
                    if isinstance(summ, str) and summ.strip():
                        changes_lines.append(f"summary: {summ.strip()}")
                except Exception:
                    pass
                if isinstance(ids2, list):
                    for aid in ids2[:20]:
                        if not isinstance(aid, str) or not aid:
                            continue
                        a = await store.get_learning_artifact(aid)
                        if not isinstance(a, dict) or str(a.get("kind") or "") != "skill_evolution":
                            continue
                        payload_a = a.get("payload") if isinstance(a.get("payload"), dict) else {}
                        if isinstance(payload_a.get("suggestion"), str) and payload_a.get("suggestion"):
                            changes_lines.append(f"- suggestion: {payload_a.get('suggestion')[:300]}")
                        evo = payload_a.get("evolution") if isinstance(payload_a.get("evolution"), dict) else None
                        if isinstance(evo, dict):
                            reason = evo.get("reason") or evo.get("trigger") or evo.get("type")
                            if reason:
                                changes_lines.append(f"- evolution: {str(reason)[:200]}")
                        sv = payload_a.get("skill_version") if isinstance(payload_a.get("skill_version"), dict) else None
                        if isinstance(sv, dict) and sv.get("diff"):
                            changes_lines.append(f"- diff: {str(sv.get('diff'))[:300]}")

                new_version = None
                try:
                    if hasattr(mgr2, "create_version"):
                        await mgr2.create_version(wsid, changes="\n".join(changes_lines)[:2000])  # type: ignore[attr-defined]
                        try:
                            s2 = await mgr2.get_skill(wsid)
                            new_version = getattr(s2, "version", None) if s2 else None
                        except Exception:
                            new_version = None
                except Exception:
                    new_version = None

                meta = getattr(target_skill, "metadata", None) if target_skill else None
                gov = meta.get("governance") if isinstance(meta, dict) and isinstance(meta.get("governance"), dict) else {}
                gov2 = dict(gov)
                gov2.update(
                    {
                        "status": "published",
                        "published_candidate_id": candidate_id,
                        "published_at": now,
                        "updated_at": now,
                        "published_skill_id": wsid,
                        "published_skill_version": new_version,
                        "rollback_to_skill_version": old_version,
                    }
                )
                await mgr2.update_skill(
                    wsid,
                    metadata={
                        "governance": gov2,
                        "learning": {"published_candidate_id": candidate_id, "published_at": now, "artifact_ids": ids2 if isinstance(ids2, list) else [], "changes": "\n".join(changes_lines)[:2000]},
                    },
                )
                try:
                    await mgr.set_artifact_status(
                        artifact_id=candidate_id,
                        status="published",
                        metadata_update={"published_workspace_skill_id": wsid, "published_skill_version": new_version, "rollback_to_skill_version": old_version},
                    )
                except Exception:
                    pass
    except Exception:
        pass

    rollout = (request or {}).get("rollout") if isinstance(request, dict) else None
    rr = None
    if isinstance(rollout, dict) and tenant_id:
        try:
            target_type = str(cand.get("target_type") or "")
            target_id = str(cand.get("target_id") or "")
            mode = str(rollout.get("mode") or "percentage")
            percentage = rollout.get("percentage")
            enabled = bool(rollout.get("enabled", True))
            include_actor_ids = rollout.get("include_actor_ids") if isinstance(rollout.get("include_actor_ids"), list) else None
            exclude_actor_ids = rollout.get("exclude_actor_ids") if isinstance(rollout.get("exclude_actor_ids"), list) else None
            if target_type and target_id:
                rr = await store.upsert_release_rollout(
                    tenant_id=str(tenant_id),
                    target_type=target_type,
                    target_id=target_id,
                    candidate_id=str(candidate_id),
                    mode=mode,
                    percentage=int(percentage) if percentage is not None else None,
                    include_actor_ids=include_actor_ids,
                    exclude_actor_ids=exclude_actor_ids,
                    enabled=enabled,
                    metadata={"published_at": now, "published_by": actor0.get("actor_id"), "source": "publish_release_candidate"},
                )
        except Exception:
            rr = None

    try:
        await record_changeset(
            store=store,
            name="learning.release.publish",
            target_type="change",
            target_id=change_id,
            status="success",
            args={"candidate_id": candidate_id, "targets": [{"type": cand.get("target_type"), "id": cand.get("target_id")}]},
            approval_request_id=str(approval_request_id) if approval_request_id else None,
            user_id=str(actor0.get("actor_id") or "admin"),
            tenant_id=str(actor0.get("tenant_id") or "") or None,
            session_id=str(actor0.get("session_id") or "") or None,
        )
    except Exception:
        pass

    out: Dict[str, Any] = {
        "status": "published",
        "candidate_id": candidate_id,
        "approval_request_id": approval_request_id,
        "change_id": change_id,
        "links": governance_links(change_id=change_id, approval_request_id=str(approval_request_id) if approval_request_id else None),
    }
    if rr is not None:
        out["rollout"] = rr
    return out


@router.post("/learning/releases/{candidate_id}/rollback")
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
    except Exception:
        pass

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
            except Exception:
                pass
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
    except Exception:
        pass

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
                    except Exception:
                        pass

            if target_skill and mgr2:
                meta = getattr(target_skill, "metadata", None) if target_skill else None
                gov = meta.get("governance") if isinstance(meta, dict) and isinstance(meta.get("governance"), dict) else {}
                gov2 = dict(gov)
                if gov2.get("published_candidate_id") == candidate_id:
                    gov2.pop("published_candidate_id", None)
                    gov2.pop("published_at", None)
                gov2.update({"status": "rolled_back", "rolled_back_candidate_id": candidate_id})
                await mgr2.update_skill(wsid, metadata={"governance": gov2})
    except Exception:
        pass

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
    except Exception:
        pass

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
    except Exception:
        pass

    return {"status": "rolled_back", "candidate_id": candidate_id, "approval_request_id": approval_request_id, "change_id": change_id, "links": governance_links(change_id=change_id, approval_request_id=str(approval_request_id) if approval_request_id else None)}

