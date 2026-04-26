from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from core.api.deps.rbac import actor_from_http, rbac_guard
from core.api.utils.governance import change_links, gate_error_envelope, ui_url
from core.api.utils.run_contract import wrap_execution_result_as_run_summary
from core.harness.kernel.runtime import get_kernel_runtime


router = APIRouter()


def _rt():
    return get_kernel_runtime()


def _store():
    rt = _rt()
    return getattr(rt, "execution_store", None) if rt else None


def _approval_mgr():
    rt = _rt()
    return getattr(rt, "approval_manager", None) if rt else None


@router.get("/approvals")
async def list_approvals(
    status: Optional[str] = None,
    tenant_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    run_id: Optional[str] = None,
    operation: Optional[str] = None,
    user_id: Optional[str] = None,
    include_related_counts: bool = False,
    order_by: str = "created_at",
    order_dir: str = "desc",
    limit: int = 100,
    offset: int = 0,
):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    res = await store.list_approval_requests(
        status=status,
        user_id=user_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        run_id=run_id,
        operation=operation,
        include_related_counts=include_related_counts,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
    )
    # enrich with derived change linkage + UI links
    try:
        ids = [str(x.get("request_id")) for x in (res.get("items") or []) if isinstance(x, dict) and x.get("request_id")]
        mapping = await store.get_change_linkages_for_approval_request_ids(ids)
        out_items = []
        for it in res.get("items") or []:
            if not isinstance(it, dict):
                continue
            aid = str(it.get("request_id") or "")
            lk = mapping.get(aid) or {}
            cid = lk.get("change_id")
            it2 = dict(it)
            if cid:
                it2["change_id"] = str(cid)
                it2["change_links"] = change_links(str(cid))
            out_items.append(it2)
        res["items"] = out_items
    except Exception:
        pass
    return res


@router.get("/approvals/pending")
async def list_pending_approvals(
    user_id: Optional[str] = None,
    order_by: str = "priority_score",
    order_dir: str = "desc",
    limit: int = 200,
    offset: int = 0,
):
    mgr = _approval_mgr()
    if not mgr:
        raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
    store = _store()
    if store:
        res = await store.list_approval_requests(
            status="pending",
            user_id=user_id,
            include_related_counts=True,
            order_by=order_by,
            order_dir=order_dir,
            limit=limit,
            offset=offset,
        )
        try:
            ids = [str(x.get("request_id")) for x in (res.get("items") or []) if isinstance(x, dict) and x.get("request_id")]
            mapping = await store.get_change_linkages_for_approval_request_ids(ids)
            out_items = []
            for it in res.get("items") or []:
                if not isinstance(it, dict):
                    continue
                aid = str(it.get("request_id") or "")
                lk = mapping.get(aid) or {}
                cid = lk.get("change_id")
                it2 = dict(it)
                if cid:
                    it2["change_id"] = str(cid)
                    it2["change_links"] = change_links(str(cid))
                out_items.append(it2)
            res["items"] = out_items
        except Exception:
            pass
        return res

    # Fallback: memory-only (rare)
    out = []
    try:
        items = mgr.get_pending_requests(user_id=user_id)
        for r in items:
            out.append(
                {
                    "request_id": r.request_id,
                    "user_id": r.user_id,
                    "operation": r.operation,
                    "status": r.status.value,
                    "details": r.details,
                    "rule_id": r.rule_id,
                    "rule_type": r.rule_type.value if r.rule_type else None,
                    "is_first_time": r.is_first_time,
                    "created_at": r.created_at.isoformat(),
                    "updated_at": r.updated_at.isoformat(),
                    "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                    "metadata": r.metadata,
                }
            )
    except Exception:
        pass
    return {"items": out, "total": len(out)}


@router.get("/approvals/{request_id}")
async def get_approval_request(request_id: str):
    mgr = _approval_mgr()
    if not mgr:
        raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
    r = await mgr.get_request_async(str(request_id)) if hasattr(mgr, "get_request_async") else mgr.get_request(str(request_id))
    if not r:
        raise HTTPException(status_code=404, detail="Approval request not found")
    resp: Dict[str, Any] = {
        "request_id": r.request_id,
        "user_id": r.user_id,
        "operation": r.operation,
        "status": r.status.value,
        "details": r.details,
        "rule_id": r.rule_id,
        "rule_type": r.rule_type.value if r.rule_type else None,
        "is_first_time": r.is_first_time,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
        "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        "metadata": r.metadata,
        "result": {
            "decision": r.result.decision.value,
            "comments": r.result.comments,
            "approved_by": r.result.approved_by,
            "timestamp": r.result.timestamp.isoformat(),
        }
        if r.result
        else None,
    }

    store = _store()
    if store:
        try:
            calls = await store.list_syscall_events(approval_request_id=request_id, limit=200, offset=0)
        except Exception:
            calls = {"items": [], "total": 0}
        try:
            execs = await store.list_agent_executions_by_approval_request_id(request_id, limit=50, offset=0)
        except Exception:
            execs = {"items": [], "total": 0}

        resp["related"] = {"agent_executions": execs, "syscall_events": calls}
        resp.setdefault("links", {})
        resp["links"]["audit_ui"] = ui_url(f"/diagnostics/audit?request_id={str(request_id)}")
        try:
            lk = await store.get_change_linkages_for_approval_request_ids([str(request_id)])
            one = lk.get(str(request_id)) or {}
            cid = one.get("change_id")
            if cid:
                resp["change_id"] = str(cid)
                resp["links"].update(change_links(str(cid)))
        except Exception:
            pass

    return resp


@router.get("/approvals/{request_id}/audit")
async def get_approval_audit(request_id: str):
    # backward-compatible alias
    return await get_approval_request(request_id)


@router.post("/approvals/{request_id}/approve")
async def approve_request(request_id: str, request: dict, http_request: Request):
    mgr = _approval_mgr()
    if not mgr:
        raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
    deny = await rbac_guard(
        http_request=http_request,
        payload=request if isinstance(request, dict) else None,
        action="approve",
        resource_type="approval_request",
        resource_id=str(request_id),
    )
    if deny:
        return deny

    # SLA enforcement: disallow approving expired requests (product-level).
    try:
        r0 = await mgr.get_request_async(str(request_id)) if hasattr(mgr, "get_request_async") else mgr.get_request(str(request_id))
        if r0 and getattr(r0, "expires_at", None) and getattr(r0, "status", None):
            from datetime import datetime
            from core.harness.infrastructure.approval.types import RequestStatus

            expired = False
            try:
                expired = bool(r0.is_expired())
            except Exception:
                expired = False
            if r0.status in (RequestStatus.EXPIRED,) or (r0.status == RequestStatus.PENDING and expired and datetime.utcnow() > r0.expires_at):
                raise HTTPException(
                    status_code=409,
                    detail=gate_error_envelope(
                        code="approval_expired",
                        message="approval_request_expired",
                        approval_request_id=str(request_id),
                        next_actions=[{"type": "refresh", "label": "刷新"}],
                    ),
                )
    except HTTPException:
        raise
    except Exception:
        pass

    approved_by = (request or {}).get("approved_by", "admin")
    comments = (request or {}).get("comments", "")
    updated = await mgr.approve(request_id=request_id, approved_by=approved_by, comments=comments)
    if not updated:
        raise HTTPException(status_code=404, detail="Approval request not found")

    store = _store()
    # PR-08: run_events linkage (best-effort)
    try:
        meta = updated.metadata if isinstance(getattr(updated, "metadata", None), dict) else {}
        if store and meta.get("run_id"):
            await store.append_run_event(
                run_id=str(meta.get("run_id")),
                event_type="approval_approved",
                trace_id=None,
                tenant_id=str(meta.get("tenant_id")) if meta.get("tenant_id") else None,
                payload={"approval_request_id": str(request_id), "approved_by": str(approved_by), "comments": str(comments or "")},
            )
    except Exception:
        pass

    if store:
        try:
            actor0 = actor_from_http(http_request, request if isinstance(request, dict) else None)
            await store.add_audit_log(
                action="approval_approve",
                status="ok",
                tenant_id=str(actor0.get("tenant_id") or "") or None,
                actor_id=str(approved_by),
                actor_role=str(actor0.get("actor_role") or "") or None,
                resource_type="approval_request",
                resource_id=str(request_id),
                detail={"comments": comments},
            )
        except Exception:
            pass
    return {"status": updated.status.value, "request_id": updated.request_id}


@router.post("/approvals/{request_id}/reject")
async def reject_request(request_id: str, request: dict, http_request: Request):
    mgr = _approval_mgr()
    if not mgr:
        raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
    deny = await rbac_guard(
        http_request=http_request,
        payload=request if isinstance(request, dict) else None,
        action="reject",
        resource_type="approval_request",
        resource_id=str(request_id),
    )
    if deny:
        return deny

    rejected_by = (request or {}).get("rejected_by", "admin")
    comments = (request or {}).get("comments", "")
    updated = await mgr.reject(request_id=request_id, rejected_by=rejected_by, comments=comments)
    if not updated:
        raise HTTPException(status_code=404, detail="Approval request not found")

    store = _store()
    # PR-08: run_events linkage (best-effort)
    try:
        meta = updated.metadata if isinstance(getattr(updated, "metadata", None), dict) else {}
        if store and meta.get("run_id"):
            await store.append_run_event(
                run_id=str(meta.get("run_id")),
                event_type="approval_rejected",
                trace_id=None,
                tenant_id=str(meta.get("tenant_id")) if meta.get("tenant_id") else None,
                payload={"approval_request_id": str(request_id), "rejected_by": str(rejected_by), "comments": str(comments or "")},
            )
    except Exception:
        pass

    if store:
        try:
            actor0 = actor_from_http(http_request, request if isinstance(request, dict) else None)
            await store.add_audit_log(
                action="approval_reject",
                status="ok",
                tenant_id=str(actor0.get("tenant_id") or "") or None,
                actor_id=str(rejected_by),
                actor_role=str(actor0.get("actor_role") or "") or None,
                resource_type="approval_request",
                resource_id=str(request_id),
                detail={"comments": comments},
            )
        except Exception:
            pass

    return {"status": updated.status.value, "request_id": updated.request_id}


@router.post("/approvals/{request_id}/replay")
async def replay_approval(request_id: str, request: dict, http_request: Request):
    """
    PR-08: Approval Hub replay

    - tool:* : replay blocked tool call with _approval_request_id injected
    - learning:* : re-run publish/rollback actions (status transitions only)
    """
    mgr = _approval_mgr()
    if not mgr:
        raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
    store = _store()
    r = await mgr.get_request_async(str(request_id)) if hasattr(mgr, "get_request_async") else mgr.get_request(str(request_id))
    if not r:
        raise HTTPException(status_code=404, detail="Approval request not found")

    from core.harness.infrastructure.approval.types import RequestStatus

    if r.status not in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED):
        change_id = None
        try:
            if store:
                lk = await store.get_change_linkages_for_approval_request_ids([str(request_id)])
                one = (lk or {}).get(str(request_id)) or {}
                change_id = one.get("change_id")
        except Exception:
            change_id = None
        raise HTTPException(
            status_code=409,
            detail=gate_error_envelope(
                code="not_approved",
                message=f"not_approved: status={r.status.value}",
                change_id=str(change_id) if change_id else None,
                approval_request_id=str(request_id),
                next_actions=[
                    x
                    for x in [
                        {"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(request_id)},
                        {"type": "open_change_control", "label": "打开变更控制台", "url": ui_url(f"/diagnostics/change-control/{change_id}")} if change_id else None,
                    ]
                    if x
                ],
            ),
        )

    op = str(r.operation or "")
    meta = r.metadata if isinstance(r.metadata, dict) else {}
    opctx = meta.get("operation_context") if isinstance(meta.get("operation_context"), dict) else {}

    # Replay tool call (best-effort). Keep compatibility by reusing HarnessIntegration.
    if op.startswith("tool:"):
        tool_name = op.split(":", 1)[1]
        tool_args = opctx.get("args") if isinstance(opctx, dict) else None
        tool_args = dict(tool_args) if isinstance(tool_args, dict) else {}
        tool_args["_approval_request_id"] = str(request_id)

        ctx = {
            "tenant_id": meta.get("tenant_id"),
            "actor_id": meta.get("actor_id") or r.user_id,
            "actor_role": meta.get("actor_role"),
            "session_id": meta.get("session_id"),
            "entrypoint": "approval_hub",
            "source": "approval_hub",
        }
        payload = {"input": tool_args, "context": ctx}

        from core.harness.integration import get_harness
        from core.harness.kernel.types import ExecutionRequest
        from core.utils.ids import new_prefixed_id

        exec_req = ExecutionRequest(
            kind="tool",
            target_id=str(tool_name),
            payload=payload,
            user_id=str(ctx.get("actor_id") or "system"),
            session_id=str(ctx.get("session_id") or "default"),
            run_id=str(meta.get("run_id") or new_prefixed_id("run")),
        )
        result = await get_harness().execute(exec_req)
        resp = wrap_execution_result_as_run_summary(result)
        return JSONResponse(status_code=200, content=resp)

    # Replay skill call (best-effort).
    if op.startswith("skill:"):
        skill_id = op.split(":", 1)[1]
        skill_args = opctx.get("args") if isinstance(opctx, dict) else None
        skill_args = dict(skill_args) if isinstance(skill_args, dict) else {}
        skill_args["_approval_request_id"] = str(request_id)

        ctx = {
            "tenant_id": meta.get("tenant_id"),
            "actor_id": meta.get("actor_id") or r.user_id,
            "actor_role": meta.get("actor_role"),
            "session_id": meta.get("session_id"),
            "entrypoint": "approval_hub",
            "source": "approval_hub",
        }
        payload = {"input": skill_args, "context": ctx}

        from core.harness.integration import get_harness
        from core.harness.kernel.types import ExecutionRequest
        from core.utils.ids import new_prefixed_id

        exec_req = ExecutionRequest(
            kind="skill",
            target_id=str(skill_id),
            payload=payload,
            user_id=str(ctx.get("actor_id") or "system"),
            session_id=str(ctx.get("session_id") or "default"),
            run_id=str(meta.get("run_id") or new_prefixed_id("run")),
        )
        result = await get_harness().execute(exec_req)
        resp = wrap_execution_result_as_run_summary(result)
        return JSONResponse(status_code=200, content=resp)

    # Replay learning release transitions / plugin runs.
    if op in ("learning:publish_release", "learning:rollback_release"):
        candidate_id = meta.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise HTTPException(status_code=400, detail="missing_candidate_id")
        if op == "learning:publish_release":
            from core.api.routers.learning_releases import publish_release_candidate

            return await publish_release_candidate(
                candidate_id=str(candidate_id),
                request={"require_approval": True, "approval_request_id": str(request_id), "user_id": r.user_id},
                http_request=http_request,
            )
        from core.api.routers.learning_releases import rollback_release_candidate

        return await rollback_release_candidate(
            candidate_id=str(candidate_id),
            request={"require_approval": True, "approval_request_id": str(request_id), "user_id": r.user_id},
            http_request=http_request,
        )

    if op == "plugin:run":
        plugin_id = meta.get("plugin_id")
        if not isinstance(plugin_id, str) or not plugin_id:
            raise HTTPException(status_code=400, detail="missing_plugin_id")
        from core.api.routers.plugins import run_plugin

        return await run_plugin(
            plugin_id=str(plugin_id),
            request={
                "approval_request_id": str(request_id),
                "run_id": meta.get("run_id"),
                "input": meta.get("input") or {},
                "session_id": meta.get("session_id"),
            },
            http_request=http_request,
        )

    # Replay gate policy apply (productized governance)
    if op == "gate_policy:apply":
        change_id = str(opctx.get("change_id") or meta.get("change_id") or "")
        if not change_id:
            raise HTTPException(status_code=400, detail="missing_change_id")
        from core.api.routers.gate_policies import apply_gate_policy_change

        return await apply_gate_policy_change(
            change_id=str(change_id),
            request={"approval_request_id": str(request_id)},
            http_request=http_request,
        )

    # Replay config publish/rollback (skill schema / permissions catalog).
    if op in ("config:publish", "config:rollback"):
        from core.services.config_registry_store import ConfigRegistryKey, get_config_registry_store

        if not isinstance(opctx, dict):
            raise HTTPException(status_code=400, detail="missing_operation_context")
        asset_type = str(opctx.get("asset_type") or "")
        scope = str(opctx.get("scope") or "workspace").strip().lower()
        tenant_id = str(opctx.get("tenant_id") or meta.get("tenant_id") or "default")
        channel = str(opctx.get("channel") or "stable").strip().lower()
        version = str(opctx.get("version") or "") or None
        to_version = str(opctx.get("to_version") or "") or None
        payload0 = opctx.get("payload")
        note = opctx.get("note") or ("approved_publish" if op == "config:publish" else "approved_rollback")
        change_id = str(opctx.get("change_id") or meta.get("change_id") or "")
        if not asset_type:
            raise HTTPException(status_code=400, detail="missing_asset_type")
        if channel not in ("stable", "canary"):
            channel = "stable"

        store2 = get_config_registry_store()
        key = ConfigRegistryKey(asset_type=asset_type, scope=scope, tenant_id=tenant_id, channel=channel)
        actor = str(meta.get("actor_id") or r.user_id or "admin")
        payload2 = payload0
        if op == "config:rollback":
            tv = to_version or version
            if tv:
                item = await store2.get_asset(asset_type=str(asset_type), scope=scope, tenant_id=tenant_id, version=str(tv))
                if item and "payload" in item:
                    payload2 = item.get("payload")
                    version = str(tv)
            v2 = await store2.publish(key=key, payload=payload2, actor=actor, note=str(note) if note else None, version=version)
        else:
            v2 = await store2.publish(key=key, payload=payload2, actor=actor, note=str(note) if note else None, version=version)

        # Emit a change control event (published) - best-effort
        try:
            storex = _store()
            if storex and change_id:
                await storex.add_syscall_event(
                    {
                        "trace_id": None,
                        "span_id": None,
                        "run_id": None,
                        "tenant_id": tenant_id,
                        "kind": "changeset",
                        "name": "config_publish_applied" if op == "config:publish" else "config_rollback_applied",
                        "status": "published" if op == "config:publish" else "rolled_back",
                        "args": {"asset_type": asset_type, "scope": scope, "channel": channel, "tenant_id": tenant_id, "to_version": v2, "note": note},
                        "result": {"version": v2},
                        "target_type": "change",
                        "target_id": change_id,
                        "user_id": actor,
                        "session_id": None,
                        "approval_request_id": str(request_id),
                    }
                )
        except Exception:
            pass
        return {
            "status": "published" if op == "config:publish" else "rolled_back",
            "asset_type": asset_type,
            "scope": scope,
            "tenant_id": tenant_id,
            "channel": channel,
            "version": v2,
            "approval_request_id": str(request_id),
        }

    raise HTTPException(status_code=400, detail=f"unsupported_operation:{op}")
