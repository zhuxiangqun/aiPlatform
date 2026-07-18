from __future__ import annotations
from core.schemas_common import MessageResponse

import os
from datetime import datetime, timezone
from typing import Any, Annotated, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from core.api.deps import actor_from_http, rbac_guard
from core.api.utils.governance import gate_error_envelope, ui_url
from core.api.utils.run_contract import wrap_execution_result_as_run_summary
from core.harness.integration import KernelRuntime, get_harness
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.kernel.types import ExecutionRequest
from core.schemas_agents import AgentCreateRequest, AgentUpdateRequest
import logging

router = APIRouter()

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]

# Legacy in-memory fallbacks (primarily for dev-mode / no ExecutionStore scenarios).
_agent_executions: Dict[str, Dict[str, Any]] = {}
_agent_history: Dict[str, List[Dict[str, Any]]] = {}
# Paused agent executions (approval_required / policy_denied) used for minimal resume.
_paused_agent_executions: Dict[str, Dict[str, Any]] = {}


def _store(rt: Optional[KernelRuntime]):
    return getattr(rt, "execution_store", None) if rt else None


def _agent_mgr(rt: Optional[KernelRuntime]):
    return getattr(rt, "agent_manager", None) if rt else None


def _resolve_skill_names(skill_ids: List[str]) -> Dict[str, str]:
    """Stub: skill name resolution is done client-side via skillApi.
    Returns IDs as-is; frontend maps them to display names from skill list."""
    return {sid: sid for sid in skill_ids}


def _approval_mgr(rt: Optional[KernelRuntime]):
    return getattr(rt, "approval_manager", None) if rt else None


def _inject_http_request_context(payload: Any, http_request: Request, *, entrypoint: str) -> Any:
    """
    Best-effort: inject tenant/actor/request identity from headers into payload.context.
    Used for tenant/actor propagation into harness/syscalls.
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
    """Enterprise audit for execute entrypoints (best-effort)."""
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


# ==================== Agent Management ====================


@router.get("/agents", response_model=Dict[str, Any])
async def list_agents(
    agent_type: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    rt: RuntimeDep = None,
):
    """List all agents (engine scope)."""
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    agents = await mgr.list_agents(agent_type, status, category, tag_list, limit, offset)
    return {
        "agents": [
            {"id": a.id, "name": a.name,
             "display_name": a.metadata.get("display_name", a.name) if isinstance(a.metadata, dict) else a.name,
             "description": a.metadata.get("description", "") if isinstance(a.metadata, dict) else "",
             "agent_type": a.type, "status": a.status,
             "category": a.category or (a.metadata.get("category", "") if isinstance(a.metadata, dict) else ""),
             "tags": a.tags or (a.metadata.get("tags", []) if isinstance(a.metadata, dict) else []),
             "phase": a.phase or (a.metadata.get("phase", "") if isinstance(a.metadata, dict) else ""),
             "config": a.config,
             "skills": a.skills,
             "skill_names": _resolve_skill_names(a.skills),
             "tools": a.tools, "metadata": a.metadata}
            for a in agents
        ],
        "total": mgr.get_agent_count().get("total", 0),
        "limit": limit,
        "offset": offset,
    }


@router.post("/agents", response_model=Dict[str, Any])
async def create_agent(request: AgentCreateRequest, rt: RuntimeDep = None):
    """Create a new agent (engine scope)."""
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    agent = await mgr.create_agent(
        name=request.name,
        agent_type=request.agent_type,
        config=request.config,
        skills=request.skills,
        tools=request.tools,
        memory_config=request.memory_config,
        metadata=request.metadata,
    )
    return {"id": agent.id, "status": "created", "name": agent.name}


@router.get("/agents/{agent_id}", response_model=Dict[str, Any])
async def get_agent(agent_id: str, rt: RuntimeDep = None):
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {
        "id": agent.id,
        "name": agent.name,
        "display_name": agent.metadata.get("display_name", agent.name) if isinstance(agent.metadata, dict) else agent.name,
        "description": agent.metadata.get("description", "") if isinstance(agent.metadata, dict) else "",
        "agent_type": agent.type,
        "status": agent.status,
        "category": agent.category or (agent.metadata.get("category", "") if isinstance(agent.metadata, dict) else ""),
        "tags": agent.tags or (agent.metadata.get("tags", []) if isinstance(agent.metadata, dict) else []),
        "phase": agent.phase or (agent.metadata.get("phase", "") if isinstance(agent.metadata, dict) else ""),
        "config": agent.config,
        "skills": agent.skills,
        "skill_names": _resolve_skill_names(agent.skills),
        "tools": agent.tools,
        "metadata": agent.metadata,
    }


@router.get("/agents/{agent_id}/sop", response_model=Dict[str, Any])
async def get_agent_sop(agent_id: str, rt: RuntimeDep = None):
    """Get agent SOP (Markdown) from AGENT.md body."""
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    data = await mgr.get_agent_sop(agent_id)
    if not data:
        raise HTTPException(status_code=404, detail="SOP not found")
    return data


@router.put("/agents/{agent_id}", response_model=Dict[str, Any])
async def update_agent(agent_id: str, request: AgentUpdateRequest, rt: RuntimeDep = None):
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    try:
        agent = await mgr.update_agent(
            agent_id,
            name=request.name,
            status=request.status,
            config=request.config,
            skills=request.skills,
            tools=request.tools,
            memory_config=request.memory_config,
            metadata=request.metadata,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "updated", "id": agent_id}


@router.delete("/agents/{agent_id}", response_model=MessageResponse)
async def delete_agent(agent_id: str, rt: RuntimeDep = None):
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    try:
        ok = await mgr.delete_agent(agent_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "deleted", "id": agent_id}


@router.post("/agents/{agent_id}/start", response_model=Dict[str, Any])
async def start_agent(agent_id: str, rt: RuntimeDep = None):
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    ok = await mgr.start_agent(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "started", "id": agent_id}


@router.post("/agents/{agent_id}/stop", response_model=Dict[str, Any])
async def stop_agent(agent_id: str, rt: RuntimeDep = None):
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    ok = await mgr.stop_agent(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "stopped", "id": agent_id}


# ==================== skills/tools bindings ====================


@router.get("/agents/{agent_id}/skills", response_model=Dict[str, Any])
async def get_agent_skills(agent_id: str, rt: RuntimeDep = None):
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    bindings = await mgr.get_skill_bindings(agent_id)
    return {
        "skills": [
            {"skill_id": b.skill_id, "skill_name": b.skill_name, "skill_type": b.skill_type, "call_count": b.call_count, "success_rate": b.success_rate}
            for b in bindings
        ],
        "skill_ids": agent.skills,
        "total": len(agent.skills),
    }


@router.post("/agents/{agent_id}/skills", response_model=Dict[str, Any])
async def bind_agent_skills(agent_id: str, request: dict, rt: RuntimeDep = None):
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    skill_ids = (request or {}).get("skill_ids", [])
    if skill_ids:
        await mgr.bind_skills(agent_id, skill_ids)
    return {"status": "bound", "skill_ids": skill_ids}


@router.delete("/agents/{agent_id}/skills/{skill_id}", response_model=Dict[str, Any])
async def unbind_agent_skill(agent_id: str, skill_id: str, rt: RuntimeDep = None):
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    await mgr.unbind_skill(agent_id, skill_id)
    return {"status": "unbound"}


@router.get("/agents/{agent_id}/tools", response_model=Dict[str, Any])
async def get_agent_tools(agent_id: str, rt: RuntimeDep = None):
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    bindings = await mgr.get_tool_bindings(agent_id)
    return {
        "tools": [
            {"tool_id": b.tool_id, "tool_name": b.tool_name, "tool_type": b.tool_type, "call_count": b.call_count, "success_rate": b.success_rate}
            for b in bindings
        ],
        "tool_ids": agent.tools,
        "total": len(agent.tools),
    }


@router.post("/agents/{agent_id}/tools", response_model=Dict[str, Any])
async def bind_agent_tools(agent_id: str, request: dict, rt: RuntimeDep = None):
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    tool_ids = (request or {}).get("tool_ids", [])
    if tool_ids:
        await mgr.bind_tools(agent_id, tool_ids)
    return {"status": "bound", "tool_ids": tool_ids}


@router.delete("/agents/{agent_id}/tools/{tool_id}", response_model=Dict[str, Any])
async def unbind_agent_tool(agent_id: str, tool_id: str, rt: RuntimeDep = None):
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    await mgr.unbind_tool(agent_id, tool_id)
    return {"status": "unbound"}


# ==================== execute / resume / execution store views ====================


@router.post("/agents/{agent_id}/execute", response_model=Dict[str, Any])
async def execute_agent(agent_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    """Execute agent (engine scope)."""
    payload = _inject_http_request_context(dict(request or {}), http_request, entrypoint="api")
    deny = await rbac_guard(http_request=http_request, payload=payload, action="execute", resource_type="agent", resource_id=str(agent_id))
    if deny:
        return deny

    ctx0 = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    user_id = payload.get("user_id") or (ctx0.get("actor_id") if isinstance(ctx0, dict) else None) or "system"
    session_id = payload.get("session_id") or (ctx0.get("session_id") if isinstance(ctx0, dict) else None) or "default"

    exec_req = ExecutionRequest(kind="agent", target_id=agent_id, payload=payload, user_id=str(user_id), session_id=str(session_id))
    result = await get_harness().execute(exec_req)
    resp = wrap_execution_result_as_run_summary(result)

    # Inject run_id for frontend feedback tracking
    run_id = resp.get("run_id", "")
    if run_id:
        try:
            from core.services.implicit_feedback import get_implicit_feedback_collector
            collector = get_implicit_feedback_collector()
            await collector.record(run_id=run_id, signal_type="response_delivered", session_id=session_id)
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    # Cache paused requests in memory (minimal resume semantics).
    try:
        payload2 = result.payload or {}
        if payload2.get("status") in ("approval_required", "policy_denied"):
            exec_id = payload2.get("execution_id")
            approval_id = None
            loop_snapshot = None
            try:
                meta0 = payload2.get("metadata") if isinstance(payload2.get("metadata"), dict) else {}
                approval_id = ((meta0.get("approval") or {}).get("approval_request_id")) if isinstance(meta0.get("approval"), dict) else None
                loop_snapshot = meta0.get("loop_state_snapshot")
            except Exception:
                approval_id = None
                loop_snapshot = None
            if exec_id:
                _paused_agent_executions[exec_id] = {
                    "agent_id": agent_id,
                    "request": request or {},
                    "user_id": (request or {}).get("user_id", "system"),
                    "session_id": (request or {}).get("session_id", "default"),
                    "approval_request_id": approval_id,
                    "loop_state_snapshot": loop_snapshot,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                _agent_executions[exec_id] = payload2
            # EnterpriseGateway: notify on approval-required events
            if payload2.get("status") == "approval_required":
                try:
                    from core.gateway import get_enterprise_gateway, GatewayMessage
                    gw = get_enterprise_gateway()
                    if gw._adapters:
                        msg_text = f"Agent '{agent_id}' requires approval.\n"
                        msg_text += f"Request: {str(request.get('message', request.get('task', '')))[:200]}\n"
                        msg_text += f"Execution ID: {exec_id}\n"
                        msg = GatewayMessage(channel="feishu", channel_chat_id="default", text=msg_text)
                        await gw.handle_message(msg)
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    try:
        await _audit_execute(rt, http_request=http_request, payload=payload, resource_type="agent", resource_id=str(agent_id), resp=resp)
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    return JSONResponse(
        status_code=200 if resp.get("ok") else int(getattr(result, "http_status", 500) or 500),
        content=resp,
        headers={"X-AIPLAT-RUN-ID": run_id} if run_id else None,
    )


@router.post("/agents/executions/{execution_id}/resume", response_model=Dict[str, Any])
async def resume_agent_execution(execution_id: str, request: dict, rt: RuntimeDep = None):
    """
    Minimal resume: re-run the original execution request after approval is granted.

    Notes:
    - Supports checkpointed resume when loop_state_snapshot exists (Phase 3.5).
    - Falls back to persisted kernel_resume payload in ExecutionStore on restart.
    """
    paused = _paused_agent_executions.get(execution_id)
    agent_id = None
    original_request: Optional[Dict[str, Any]] = None
    approval_id = None

    if paused:
        agent_id = paused.get("agent_id")
        original_request = paused.get("request") or {}
        approval_id = paused.get("approval_request_id")
    else:
        store = _store(rt)
        if not store:
            raise HTTPException(status_code=404, detail="Paused execution not found (no in-memory state and no store)")
        rec = await store.get_agent_execution(execution_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Paused execution not found (execution not in store)")
        meta = rec.get("metadata") if isinstance(rec.get("metadata"), dict) else {}
        kr = (meta or {}).get("kernel_resume") if isinstance(meta, dict) else None
        if not isinstance(kr, dict):
            raise HTTPException(status_code=409, detail="Execution found but has no resumable payload")
        agent_id = rec.get("agent_id")
        original_request = {
            "messages": kr.get("messages", []),
            "context": kr.get("context", {}),
            "session_id": kr.get("session_id", "default"),
            "user_id": kr.get("user_id", "system"),
        }
        approval_id = ((meta or {}).get("approval") or {}).get("approval_request_id") if isinstance((meta or {}).get("approval"), dict) else None

    if not agent_id or not isinstance(original_request, dict):
        raise HTTPException(status_code=500, detail="Invalid paused execution record")

    # If there is an approval request, ensure it is resolved/approved
    if approval_id:
        approval_mgr = _approval_mgr(rt)
        if not approval_mgr:
            raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
        ar = (
            await approval_mgr.get_request_async(str(approval_id))
            if hasattr(approval_mgr, "get_request_async")
            else approval_mgr.get_request(str(approval_id))
        )
        if not ar:
            raise HTTPException(status_code=404, detail=f"Approval request not found: {approval_id}")
        from core.harness.infrastructure.approval.types import RequestStatus

        if ar.status not in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED):
            change_id = None
            try:
                store = _store(rt)
                if store:
                    lk = await store.get_change_linkages_for_approval_request_ids([str(approval_id)])
                    one = (lk or {}).get(str(approval_id)) or {}
                    change_id = one.get("change_id")
            except Exception:
                change_id = None
            raise HTTPException(  # noqa: error-structured
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message=f"not_approved: status={ar.status.value}",
                    change_id=str(change_id) if change_id else None,
                    approval_request_id=str(approval_id),
                    next_actions=[
                        {"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(approval_id)},
                        {"type": "open_change_control", "label": "打开变更控制台", "url": ui_url(f"/diagnostics/change-control/{change_id}")} if change_id else None,
                    ],
                    detail={"approval_status": ar.status.value},
                ),
            )

    # Phase 22: OperatorAgent decision confirmation (approve/reject)
    paused_phase = (paused or {}).get("_paused_phase")
    if paused_phase == "operator_confirmation":
        # Timeout check
        created_at_str = str((paused or {}).get("created_at", ""))
        ttl = int((paused or {}).get("ttl_seconds", 3600))
        try:
            from datetime import datetime, timezone
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - created_at.replace(tzinfo=timezone.utc)).total_seconds() > ttl:
                _paused_agent_executions.pop(execution_id, None)
                return {"status": "timeout", "message": f"审批超时 ({ttl}s)，已自动拒绝"}
        except Exception:
            pass

        action = str(((request or {}) if isinstance(request, dict) else {}).get("action", "approve"))
        decision = (paused or {}).get("_decision_snapshot")
        original_question = str((paused or {}).get("_original_question", ""))

        if action == "approve" and decision:
            try:
                from core.harness.actions.action_bridge import execute_decision_actions
                ctx = {
                    "entity_id": str((paused.get("request", {}) or {}).get("entity", "")),
                    "domain_id": str((paused.get("request", {}) or {}).get("domain_id", "default")),
                    "timestamp": str(int(time.time())),
                }
                action_results = await execute_decision_actions(decision, context=ctx)
                _paused_agent_executions.pop(execution_id, None)
                return {"status": "approved", "action_results": action_results}
            except Exception as e:
                _paused_agent_executions.pop(execution_id, None)
                return {"status": "approved", "error": f"action_bridge failed: {str(e)[:200]}"}

        elif action == "reject":
            feedback = str(((request or {}) if isinstance(request, dict) else {}).get("feedback", ""))
            _paused_agent_executions.pop(execution_id, None)
            exec_req = ExecutionRequest(
                kind="agent",
                target_id="operator_agent",
                payload={
                    "messages": [{"role": "user", "content": original_question}],
                    "context": {"_reject_feedback": feedback or "决策被人工拒绝，请重新生成"},
                    "session_id": paused.get("session_id", "default"),
                    "user_id": paused.get("user_id", "system"),
                },
            )
            result = await get_harness().execute(exec_req)
            return {"status": "rejected_and_regenerated", "ok": result.ok}

        else:
            return {"status": "error", "message": f"未知操作: {action}，请传 action=approve 或 action=reject"}

    # Prefer checkpointed resume when available:
    loop_snapshot = None
    try:
        loop_snapshot = paused.get("loop_state_snapshot") if paused else None
        if loop_snapshot is None and _store(rt):
            rec = await _store(rt).get_agent_execution(execution_id)
            meta = (rec or {}).get("metadata") if isinstance((rec or {}).get("metadata"), dict) else None
            loop_snapshot = (meta or {}).get("loop_state_snapshot") if isinstance(meta, dict) else None
    except Exception:
        loop_snapshot = None

    payload = dict(original_request or {})
    if loop_snapshot is not None:
        payload["_resume_loop_state"] = loop_snapshot

    exec_req = ExecutionRequest(
        kind="agent",
        target_id=agent_id,
        payload=payload,
        user_id=original_request.get("user_id", "system"),
        session_id=original_request.get("session_id", "default"),
    )
    result = await get_harness().execute(exec_req)
    if not result.ok:
        raise HTTPException(status_code=result.http_status, detail=result.error or "Execution failed")

    # On successful resume, optionally drop the paused entry
    try:
        if (result.payload or {}).get("status") == "completed":
            _paused_agent_executions.pop(execution_id, None)
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    payload2 = result.payload or {}
    payload2["resumed_from_execution_id"] = execution_id
    payload2["approval_request_id"] = approval_id
    return payload2


@router.get("/agents/executions/{execution_id}", response_model=Dict[str, Any])
async def get_agent_execution(execution_id: str, rt: RuntimeDep = None):
    """Get agent execution record."""
    store = _store(rt)
    execution = await store.get_agent_execution(execution_id) if store else None
    if not execution:
        execution = _agent_executions.get(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
    return execution


@router.get("/agents/{agent_id}/history", response_model=Dict[str, Any])
async def get_agent_history(agent_id: str, limit: int = 100, offset: int = 0, rt: RuntimeDep = None):
    """Get agent execution history."""
    store = _store(rt)
    if store:
        history, total = await store.list_agent_history(agent_id, limit=limit, offset=offset)
        return {"history": history, "total": total}
    history = _agent_history.get(agent_id, [])[offset : offset + limit]
    return {"history": history, "total": len(_agent_history.get(agent_id, []))}


@router.get("/agents/{agent_id}/versions", response_model=Dict[str, Any])
async def get_agent_versions(agent_id: str, rt: RuntimeDep = None):
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    versions = await mgr.get_versions(agent_id)
    return {"agent_id": agent_id, "versions": [{"version": v.version, "status": v.status, "created_at": v.created_at.isoformat(), "changes": v.changes} for v in versions]}


@router.post("/agents/{agent_id}/versions", response_model=Dict[str, Any])
async def create_agent_version(agent_id: str, request: dict, rt: RuntimeDep = None):
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    changes = (request or {}).get("changes", "")
    version = await mgr.create_version(agent_id, changes)
    if not version:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"version": version.version, "status": version.status, "created_at": version.created_at.isoformat(), "changes": version.changes}


@router.post("/agents/{agent_id}/versions/{version}/rollback", response_model=Dict[str, Any])
async def rollback_agent_version(agent_id: str, version: str, rt: RuntimeDep = None):
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    ok = await mgr.rollback_version(agent_id, version)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent or version {version} not found")
    return {"status": "rolled_back", "version": version}


# ── Models catalog (for agent editor dropdowns) ──

@router.get("/models", response_model=Dict[str, Any])
async def list_models():
    """List available LLM models grouped by provider (for agent editor dropdown)."""
    try:
        from core.api.facades.skill_tool_facade import get_model_manager
        registry = get_model_manager()
        # infra ModelManager returns models as list of objects
        if hasattr(registry, '_models'):
            entries = [{"name": m.name, "provider": m.provider, "enabled": m.enabled, "type": m.type.value if hasattr(m.type, 'value') else str(m.type)}
                       for m in registry._models.values()]
        else:
            entries = registry.list_all_entries() if hasattr(registry, 'list_all_entries') else []
        groups: Dict[str, list] = {}
        for e in entries:
            provider = e.get("provider", "unknown")
            groups.setdefault(provider, []).append(e)
        return {"models": entries, "by_provider": groups}
    except Exception:
        # Fallback: return models from centralized model resolution
        from core.harness.utils.model_injection import get_default_model
        models = []
        for purpose in ("chat", "agent"):
            name = get_default_model(purpose=purpose) or ""
            models.append({"name": name, "provider": "deepseek"})
        return {"models": models, "by_provider": {"deepseek": models}}

@router.get("/approvals/pending", response_model=Dict[str, Any])
async def list_pending_approvals(request: Request):
    """兼容端点 — 返回空审批列表（新审批系统由 management 审批中心接管）"""
    _ = request
    return {"items": [], "total": 0}


@router.post("/agents/feedback", response_model=Dict[str, Any])
async def submit_agent_feedback(body: dict, request: Request):
    """Phase 4.2: Submit implicit feedback signal for a previous agent execution.

    Accepts: {run_id, signal_type, session_id}
    Signals: copy_full, select_text, re_query, repeat_query, abandon

    Frontend sends this after user interaction with the answer.
    """
    run_id = str((body or {}).get("run_id", "")).strip()
    signal_type = str((body or {}).get("signal_type", "")).strip()
    session_id = str((body or {}).get("session_id", "")).strip()

    if not run_id or not signal_type:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="run_id and signal_type required")

    valid_signals = {"copy_full", "select_text", "re_query", "repeat_query", "abandon"}
    if signal_type not in valid_signals:
        from fastapi import HTTPException
        raise HTTPException(status_code=422,
                            detail=f"signal_type must be one of: {', '.join(sorted(valid_signals))}")

    try:
        from core.services.implicit_feedback import get_implicit_feedback_collector
        collector = get_implicit_feedback_collector()
        await collector.record(run_id=run_id, signal_type=signal_type, session_id=session_id)
        return {"ok": True, "run_id": run_id, "signal_type": signal_type}
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/hallucination/dashboard", response_model=Dict[str, Any])
async def get_hallucination_dashboard(domain_id: str = "default"):
    """Phase 3.1: Get hallucination tracking dashboard."""
    try:
        from core.harness.evaluation.hallucination_tracker import get_hallucination_tracker
        tracker = get_hallucination_tracker()
        return {
            "dashboard": tracker.get_dashboard(domain_id=domain_id),
            "recent_reports": tracker.get_recent_reports(limit=20),
        }
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/feedback/stats", response_model=Dict[str, Any])
async def get_feedback_stats():
    """Phase 4.2: Get implicit feedback statistics."""
    try:
        from core.services.implicit_feedback import get_implicit_feedback_collector
        collector = get_implicit_feedback_collector()
        return collector.get_stats()
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


# ── v2.2: HITL override — human veto on autoreview clean judgment ──

@router.post("/agents/{agent_id}/override-autoreview", response_model=Dict[str, Any])
async def override_autoreview(agent_id: str, body: Dict[str, Any]):
    """人工否决 autoreview 的 clean 判断并触发 deep mode 重新审查。

    Body: { "target": "diff", "reason": "misdiagnosed security issue", "actor_id": "admin" }
    """
    target = body.get("target", "diff")
    reason = body.get("reason", "")
    actor = body.get("actor_id", "system")
    import time as _time

    try:
        from core.services.execution_store import get_execution_store
        store = get_execution_store()
        await store.upsert_global_setting(
            key=f"autoreview:override:{actor}:{int(_time.time())}",
            value={
                "target": target, "reason": reason, "actor": actor,
                "agent_id": agent_id, "timestamp": _time.time(),
            },
        )
        from core.engine.skills.autoreview.handler import execute
        return await execute({"target": target, "mode": "deep", "focus": "security"})
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


# ── Phase 22 G2: Pipeline HITL REST endpoint ──

@router.post("/pipelines/{pipeline_id}/hitl-resolve", response_model=Dict[str, Any])
async def resolve_pipeline_hitl(pipeline_id: str, request: dict):
    """Approve or reject a paused pipeline stage.

    Body: {"action": "approve"|"reject", "feedback": "optional comment"}
    """
    action = str(request.get("action", "approve")).lower()
    feedback = str(request.get("feedback", ""))
    try:
        from core.services.builder_project_service import get_running_pipeline
        engine = await get_running_pipeline(pipeline_id)
        if not engine:
            raise HTTPException(status_code=404, detail="pipeline_not_found")
        if action == "approve":
            await engine.approve(engine._state, feedback=feedback)
            return {"status": "approved", "pipeline_id": pipeline_id}
        elif action == "reject":
            await engine.reject(engine._state)
            return {"status": "rejected", "pipeline_id": pipeline_id, "feedback": feedback}
        else:
            raise HTTPException(status_code=400, detail=f"unknown action: {action}")
    except HTTPException:
        raise
    except HTTPException:
        raise
        raise HTTPException(status_code=500, detail=str(e)[:200])

# ── Phase 54: Runtime Pipeline Stage Adjustment ──

@router.post("/pipelines/{pipeline_id}/stages/adjust", response_model=Dict[str, Any])
async def adjust_pipeline_stage(pipeline_id: str, request: dict):
    """Runtime modification of pipeline stage configuration.
    
    Body: {"stage_id":"...","action":"modify_prompt|skip|change_agent",
           "prompt_extra":"...","agent_type":"react|plan|reflection"}
    """
    stage_id = str(request.get("stage_id", ""))
    action = str(request.get("action", "modify_prompt"))
    try:
        from core.services.builder_project_service import get_running_pipeline
        engine = await get_running_pipeline(pipeline_id)
        if not engine:
            raise HTTPException(status_code=404, detail="pipeline_not_found")
        matched = None
        for s in engine._config.stages:
            if s.id == stage_id:
                matched = s; break
        if not matched:
            raise HTTPException(status_code=404, detail=f"stage_not_found:{stage_id}")
        changes = {}
        if action == "modify_prompt":
            extra = str(request.get("prompt_extra", "")); old = matched.prompt_extra or ""
            if extra: matched.prompt_extra = old + "\n" + extra; changes["prompt"] = extra[:100]
        elif action == "skip":
            engine._state[f"_stage_{stage_id}_skipped"] = True
            engine._state[f"_stage_{stage_id}_done"] = True; changes["skipped"] = True
        elif action == "change_agent":
            t = str(request.get("agent_type","")); matched.agent_type = t; changes["agent"] = t
        return {"status":"adjusted","stage_id":stage_id,"action":action,"changes":changes}
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e)[:200])
