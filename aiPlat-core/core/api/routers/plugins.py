from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from core.api.deps.rbac import actor_from_http, rbac_guard
from core.api.utils.governance import gate_error_envelope, ui_url
from core.harness.kernel.runtime import get_kernel_runtime
from core.policy.engine import PolicyDecision, evaluate_tool_policy_snapshot
from core.schemas import RunStatus
from core.utils.ids import new_prefixed_id


router = APIRouter()


def _rt():
    return get_kernel_runtime()


def _store():
    rt = _rt()
    return getattr(rt, "execution_store", None) if rt else None


def _approval_mgr():
    rt = _rt()
    return getattr(rt, "approval_manager", None) if rt else None


def _plugin_mgr():
    rt = _rt()
    return getattr(rt, "plugin_manager", None) if rt else None


@router.get("/plugins")
async def list_plugins(http_request: Request, limit: int = 100, offset: int = 0):
    store = _store()
    plugin_mgr = _plugin_mgr()
    if not store or not plugin_mgr:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    actor0 = actor_from_http(http_request, None)
    tid = actor0.get("tenant_id")
    return await plugin_mgr.list_plugins(tenant_id=str(tid) if tid else None, limit=limit, offset=offset)


@router.put("/plugins")
async def upsert_plugin(request: dict, http_request: Request):
    store = _store()
    plugin_mgr = _plugin_mgr()
    if not store or not plugin_mgr:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    actor0 = actor_from_http(http_request, request if isinstance(request, dict) else None)
    tid = actor0.get("tenant_id")
    deny = await rbac_guard(
        http_request=http_request,
        payload=request if isinstance(request, dict) else None,
        action="upsert",
        resource_type="plugin",
        resource_id=str((request or {}).get("plugin_id") or ""),
    )
    if deny:
        return deny
    if not tid:
        raise HTTPException(status_code=400, detail="tenant_id required")
    manifest = (request or {}).get("manifest")
    if not isinstance(manifest, dict):
        raise HTTPException(status_code=400, detail="manifest must be object")
    enabled = bool((request or {}).get("enabled", False))
    rec = await plugin_mgr.upsert_plugin(tenant_id=str(tid), manifest=manifest, enabled=enabled)
    try:
        await store.add_audit_log(
            action="plugin_upsert",
            status="ok",
            tenant_id=str(tid),
            actor_id=str(actor0.get("actor_id") or "system"),
            actor_role=str(actor0.get("actor_role") or "") or None,
            resource_type="plugin",
            resource_id=str(rec.get("plugin_id")),
            detail={"name": rec.get("name"), "version": rec.get("version"), "enabled": bool(rec.get("enabled"))},
        )
    except Exception:
        pass
    return {"status": "ok", "plugin": rec}


@router.post("/plugins/{plugin_id}/enable")
async def set_plugin_enabled(plugin_id: str, request: dict, http_request: Request):
    store = _store()
    plugin_mgr = _plugin_mgr()
    if not store or not plugin_mgr:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(
        http_request=http_request,
        payload=request if isinstance(request, dict) else None,
        action="enable",
        resource_type="plugin",
        resource_id=str(plugin_id),
    )
    if deny:
        return deny
    actor0 = actor_from_http(http_request, request if isinstance(request, dict) else None)
    tid = actor0.get("tenant_id")
    if not tid:
        raise HTTPException(status_code=400, detail="tenant_id required")
    enabled = bool((request or {}).get("enabled", True))
    ok = await plugin_mgr.set_enabled(tenant_id=str(tid), plugin_id=str(plugin_id), enabled=enabled)
    if not ok:
        raise HTTPException(status_code=404, detail="plugin_not_found")
    try:
        await store.add_audit_log(
            action="plugin_enable",
            status="ok",
            tenant_id=str(tid),
            actor_id=str(actor0.get("actor_id") or "system"),
            actor_role=str(actor0.get("actor_role") or "") or None,
            resource_type="plugin",
            resource_id=str(plugin_id),
            detail={"enabled": enabled},
        )
    except Exception:
        pass
    return {"status": "ok", "plugin_id": plugin_id, "enabled": enabled}


@router.get("/plugins/{plugin_id}/versions")
async def list_plugin_versions(plugin_id: str, http_request: Request, limit: int = 50, offset: int = 0):
    plugin_mgr = _plugin_mgr()
    store = _store()
    if not store or not plugin_mgr:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    actor0 = actor_from_http(http_request, None)
    tid = actor0.get("tenant_id")
    if not tid:
        raise HTTPException(status_code=400, detail="tenant_id required")
    deny = await rbac_guard(http_request=http_request, payload=None, action="read", resource_type="plugin", resource_id=str(plugin_id))
    if deny:
        return deny
    return await plugin_mgr.list_versions(tenant_id=str(tid), plugin_id=str(plugin_id), limit=limit, offset=offset)


@router.post("/plugins/{plugin_id}/rollback")
async def rollback_plugin(plugin_id: str, request: dict, http_request: Request):
    plugin_mgr = _plugin_mgr()
    store = _store()
    if not store or not plugin_mgr:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    actor0 = actor_from_http(http_request, request if isinstance(request, dict) else None)
    tid = actor0.get("tenant_id")
    if not tid:
        raise HTTPException(status_code=400, detail="tenant_id required")
    deny = await rbac_guard(
        http_request=http_request,
        payload=request if isinstance(request, dict) else None,
        action="rollback",
        resource_type="plugin",
        resource_id=str(plugin_id),
    )
    if deny:
        return deny
    ver = (request or {}).get("version") if isinstance(request, dict) else None
    if not ver:
        raise HTTPException(status_code=400, detail="version required")
    try:
        rec = await plugin_mgr.rollback(tenant_id=str(tid), plugin_id=str(plugin_id), version=str(ver))
    except RuntimeError as e:
        if "not_found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise
    try:
        await store.add_audit_log(
            action="plugin_rollback",
            status="ok",
            tenant_id=str(tid),
            actor_id=str(actor0.get("actor_id") or "system"),
            actor_role=str(actor0.get("actor_role") or "") or None,
            resource_type="plugin",
            resource_id=str(plugin_id),
            detail={"version": str(ver)},
        )
    except Exception:
        pass
    return {"status": "ok", "plugin": rec}


async def _require_plugin_run_approval(
    *,
    approval_manager: Any,
    actor_id: str,
    plugin_id: str,
    run_id: str,
    tenant_id: Optional[str],
    actor_role: Optional[str],
    session_id: Optional[str],
    required_tools: list[str],
    input: Optional[dict] = None,
    details: str = "",
) -> str:
    from core.harness.infrastructure.approval.types import ApprovalContext, ApprovalRule, RuleType

    if not approval_manager:
        raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
    rule = ApprovalRule(
        rule_id="plugin_run",
        rule_type=RuleType.SENSITIVE_OPERATION,
        name="插件运行审批",
        description="运行 workflow/plugin 需要审批",
        priority=1,
        metadata={"sensitive_operations": ["plugin:run"]},
    )
    approval_manager.register_rule(rule)
    ctx = ApprovalContext(
        session_id=str(session_id or "default"),
        user_id=str(actor_id or "system"),
        operation="plugin:run",
        operation_context={"plugin_id": plugin_id, "details": details or f"run plugin {plugin_id}", "input": input or {}},
        metadata={
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "session_id": session_id,
            "run_id": run_id,
            "plugin_id": plugin_id,
            "required_tools": required_tools,
            "input": input or {},
            "system_run_plan": {"type": "plugin", "plugin_id": plugin_id, "required_tools": required_tools},
        },
    )
    req = approval_manager.create_request(ctx, rule=rule)
    try:
        await approval_manager._persist(req)  # type: ignore[attr-defined]
    except Exception:
        pass
    return req.request_id


@router.post("/plugins/{plugin_id}/run")
async def run_plugin(plugin_id: str, request: dict, http_request: Request):
    """
    PR-11: plugin run (MVP)
    - policy：基于 tenant policy 对 required_tools 做 allow/deny/approval_required 汇总
    - approval：需要审批时返回 waiting_approval + approval_request_id
    - execution：当前仅写 run_events/audit + 返回占位 output（后续接 workflow 执行器）
    """
    store = _store()
    plugin_mgr = _plugin_mgr()
    if not store or not plugin_mgr:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(http_request=http_request, payload=request if isinstance(request, dict) else None, action="execute", resource_type="plugin", resource_id=str(plugin_id))
    if deny:
        return deny

    actor0 = actor_from_http(http_request, request if isinstance(request, dict) else None)
    tid = actor0.get("tenant_id")
    actor_id = str(actor0.get("actor_id") or "system")
    actor_role = actor0.get("actor_role")
    if not tid:
        raise HTTPException(status_code=400, detail="tenant_id required")

    plugin = await plugin_mgr.get_plugin(tenant_id=str(tid), plugin_id=str(plugin_id))
    if not plugin:
        raise HTTPException(status_code=404, detail="plugin_not_found")
    if int(plugin.get("enabled") or 0) != 1:
        raise HTTPException(status_code=409, detail="plugin_disabled")

    manifest = plugin.get("manifest") if isinstance(plugin.get("manifest"), dict) else {}
    required_tools = manifest.get("required_tools") if isinstance(manifest.get("required_tools"), list) else []
    required_tools = [str(x) for x in required_tools if isinstance(x, (str, int, float)) and str(x).strip()]

    pol_item = await store.get_tenant_policy(tenant_id=str(tid))
    policy = pol_item.get("policy") if isinstance(pol_item, dict) and isinstance(pol_item.get("policy"), dict) else None
    policy_version = pol_item.get("version") if isinstance(pol_item, dict) else None
    try:
        policy_version = int(policy_version) if policy_version is not None else None
    except Exception:
        policy_version = None

    deny_reason = None
    approval_needed = False
    for tn in required_tools:
        ev = evaluate_tool_policy_snapshot(
            policy=policy,
            policy_version=policy_version,
            tenant_id=str(tid),
            actor_id=actor_id,
            actor_role=str(actor_role) if actor_role else None,
            tool_name=str(tn),
            tool_args={"_tenant_id": str(tid), "_actor_role": actor_role},
        )
        if ev.decision == PolicyDecision.DENY:
            deny_reason = ev.reason
            break
        if ev.decision == PolicyDecision.APPROVAL_REQUIRED:
            approval_needed = True

    approval_request_id = (request or {}).get("approval_request_id")
    run_id = str((request or {}).get("run_id") or new_prefixed_id("run"))
    session_id = (request or {}).get("session_id")
    input_obj = (request or {}).get("input") if isinstance((request or {}).get("input"), dict) else {}

    if deny_reason:
        try:
            await store.create_plugin_run(
                run_id=run_id,
                tenant_id=str(tid),
                plugin_id=str(plugin_id),
                status="failed",
                approval_request_id=str(approval_request_id) if approval_request_id else None,
                input=input_obj,
                output=None,
                error=str(deny_reason),
            )
        except Exception:
            pass
        return JSONResponse(status_code=403, content={"error": {"code": "POLICY_DENIED", "message": str(deny_reason), "detail": {"policy_version": policy_version}}})

    if approval_needed and not approval_request_id:
        approval_request_id = await _require_plugin_run_approval(
            approval_manager=_approval_mgr(),
            actor_id=actor_id,
            plugin_id=str(plugin_id),
            run_id=run_id,
            tenant_id=str(tid),
            actor_role=str(actor_role) if actor_role else None,
            session_id=str(session_id) if session_id else None,
            required_tools=required_tools,
            input=input_obj,
        )
        try:
            await store.create_plugin_run(
                run_id=run_id,
                tenant_id=str(tid),
                plugin_id=str(plugin_id),
                status="waiting_approval",
                approval_request_id=str(approval_request_id),
                input=input_obj,
                output=None,
                error="approval_required",
            )
            await store.append_run_event(
                run_id=str(run_id),
                event_type="approval_requested",
                trace_id=None,
                tenant_id=str(tid),
                payload={"kind": "plugin", "plugin_id": str(plugin_id), "approval_request_id": str(approval_request_id)},
            )
        except Exception:
            pass
        return {
            "ok": False,
            "run_id": run_id,
            "trace_id": None,
            "status": RunStatus.waiting_approval.value,
            "legacy_status": "approval_required",
            "output": None,
            "error": {"code": "APPROVAL_REQUIRED", "message": "approval_required", "detail": {"approval_request_id": approval_request_id}},
            "approval_request_id": approval_request_id,
        }

    if approval_needed and approval_request_id:
        approval_mgr = _approval_mgr()
        ar = (await approval_mgr.get_request_async(str(approval_request_id))) if (approval_mgr and hasattr(approval_mgr, "get_request_async")) else (approval_mgr.get_request(str(approval_request_id)) if approval_mgr else None)
        from core.harness.infrastructure.approval.types import RequestStatus

        if not ar:
            raise HTTPException(status_code=404, detail="approval_request_not_found")
        if ar.status not in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED):
            change_id = None
            try:
                lk = await store.get_change_linkages_for_approval_request_ids([str(approval_request_id)])
                one = (lk or {}).get(str(approval_request_id)) or {}
                change_id = one.get("change_id")
            except Exception:
                change_id = None
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message=f"not_approved: status={ar.status.value}",
                    change_id=str(change_id) if change_id else None,
                    approval_request_id=str(approval_request_id),
                    next_actions=[
                        x
                        for x in [
                            {"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(approval_request_id)},
                            {"type": "open_change_control", "label": "打开变更控制台", "url": ui_url(f"/diagnostics/change-control/{change_id}")} if change_id else None,
                        ]
                        if x
                    ],
                ),
            )

    try:
        await store.create_plugin_run(run_id=run_id, tenant_id=str(tid), plugin_id=str(plugin_id), status="running", approval_request_id=str(approval_request_id) if approval_request_id else None, input=input_obj, output=None, error=None)
        await store.append_run_event(run_id=str(run_id), event_type="run_start", trace_id=None, tenant_id=str(tid), payload={"kind": "plugin", "plugin_id": str(plugin_id), "actor_id": actor_id})
        await store.append_run_event(run_id=str(run_id), event_type="plugin_start", trace_id=None, tenant_id=str(tid), payload={"plugin_id": str(plugin_id), "required_tools": required_tools})
    except Exception:
        pass

    output = {"message": "plugin executed (mvp)", "plugin_id": str(plugin_id), "required_tools": required_tools}
    try:
        await store.create_plugin_run(run_id=run_id, tenant_id=str(tid), plugin_id=str(plugin_id), status="completed", approval_request_id=str(approval_request_id) if approval_request_id else None, input=input_obj, output=output, error=None)
        await store.append_run_event(run_id=str(run_id), event_type="plugin_end", trace_id=None, tenant_id=str(tid), payload={"plugin_id": str(plugin_id), "status": "completed"})
        await store.append_run_event(run_id=str(run_id), event_type="run_end", trace_id=None, tenant_id=str(tid), payload={"kind": "plugin", "plugin_id": str(plugin_id), "status": "completed"})
        await store.add_audit_log(action="plugin_run", status="ok", tenant_id=str(tid), actor_id=str(actor_id), actor_role=str(actor_role) if actor_role else None, resource_type="plugin", resource_id=str(plugin_id), run_id=str(run_id), detail={"required_tools": required_tools})
    except Exception:
        pass

    return {"ok": True, "run_id": run_id, "trace_id": None, "status": RunStatus.completed.value, "legacy_status": "completed", "output": output, "error": None}
