from __future__ import annotations

from datetime import datetime
from typing import Any, Annotated, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from core.api.deps.rbac import actor_from_http, rbac_guard
from core.api.utils.governance import gate_error_envelope, ui_url
from core.api.utils.run_contract import wrap_execution_result_as_run_summary
from core.harness.integration import KernelRuntime, get_harness
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.kernel.types import ExecutionRequest
from core.schemas import AgentCreateRequest, AgentUpdateRequest

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


@router.get("/agents")
async def list_agents(
    agent_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    rt: RuntimeDep = None,
):
    """List all agents (engine scope)."""
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    agents = await mgr.list_agents(agent_type, status, limit, offset)
    return {
        "agents": [
            {"id": a.id, "name": a.name, "agent_type": a.type, "status": a.status, "skills": a.skills, "tools": a.tools, "metadata": a.metadata}
            for a in agents
        ],
        "total": mgr.get_agent_count().get("total", 0),
        "limit": limit,
        "offset": offset,
    }


@router.post("/agents")
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


@router.get("/agents/{agent_id}")
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
        "agent_type": agent.type,
        "status": agent.status,
        "config": agent.config,
        "skills": agent.skills,
        "tools": agent.tools,
        "metadata": agent.metadata,
    }


@router.put("/agents/{agent_id}")
async def update_agent(agent_id: str, request: AgentUpdateRequest, rt: RuntimeDep = None):
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    try:
        agent = await mgr.update_agent(
            agent_id,
            name=request.name,
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


@router.delete("/agents/{agent_id}")
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


@router.post("/agents/{agent_id}/start")
async def start_agent(agent_id: str, rt: RuntimeDep = None):
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    ok = await mgr.start_agent(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "started", "id": agent_id}


@router.post("/agents/{agent_id}/stop")
async def stop_agent(agent_id: str, rt: RuntimeDep = None):
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    ok = await mgr.stop_agent(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "stopped", "id": agent_id}


# ==================== skills/tools bindings ====================


@router.get("/agents/{agent_id}/skills")
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


@router.post("/agents/{agent_id}/skills")
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


@router.delete("/agents/{agent_id}/skills/{skill_id}")
async def unbind_agent_skill(agent_id: str, skill_id: str, rt: RuntimeDep = None):
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    await mgr.unbind_skill(agent_id, skill_id)
    return {"status": "unbound"}


@router.get("/agents/{agent_id}/tools")
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


@router.post("/agents/{agent_id}/tools")
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


@router.delete("/agents/{agent_id}/tools/{tool_id}")
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


@router.post("/agents/{agent_id}/execute")
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
                    "created_at": datetime.utcnow().isoformat(),
                }
                _agent_executions[exec_id] = payload2
    except Exception:
        pass

    try:
        await _audit_execute(rt, http_request=http_request, payload=payload, resource_type="agent", resource_id=str(agent_id), resp=resp)
    except Exception:
        pass
    return JSONResponse(status_code=200 if resp.get("ok") else int(getattr(result, "http_status", 500) or 500), content=resp)


@router.post("/agents/executions/{execution_id}/resume")
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
            raise HTTPException(
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
    except Exception:
        pass

    payload2 = result.payload or {}
    payload2["resumed_from_execution_id"] = execution_id
    payload2["approval_request_id"] = approval_id
    return payload2


@router.get("/agents/executions/{execution_id}")
async def get_agent_execution(execution_id: str, rt: RuntimeDep = None):
    """Get agent execution record."""
    store = _store(rt)
    execution = await store.get_agent_execution(execution_id) if store else None
    if not execution:
        execution = _agent_executions.get(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
    return execution


@router.get("/agents/{agent_id}/history")
async def get_agent_history(agent_id: str, limit: int = 100, offset: int = 0, rt: RuntimeDep = None):
    """Get agent execution history."""
    store = _store(rt)
    if store:
        history, total = await store.list_agent_history(agent_id, limit=limit, offset=offset)
        return {"history": history, "total": total}
    history = _agent_history.get(agent_id, [])[offset : offset + limit]
    return {"history": history, "total": len(_agent_history.get(agent_id, []))}


@router.get("/agents/{agent_id}/versions")
async def get_agent_versions(agent_id: str, rt: RuntimeDep = None):
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    versions = await mgr.get_versions(agent_id)
    return {"agent_id": agent_id, "versions": [{"version": v.version, "status": v.status, "created_at": v.created_at.isoformat(), "changes": v.changes} for v in versions]}


@router.post("/agents/{agent_id}/versions")
async def create_agent_version(agent_id: str, request: dict, rt: RuntimeDep = None):
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    changes = (request or {}).get("changes", "")
    version = await mgr.create_version(agent_id, changes)
    if not version:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"version": version.version, "status": version.status, "created_at": version.created_at.isoformat(), "changes": version.changes}


@router.post("/agents/{agent_id}/versions/{version}/rollback")
async def rollback_agent_version(agent_id: str, version: str, rt: RuntimeDep = None):
    mgr = _agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Agent manager not available")
    ok = await mgr.rollback_version(agent_id, version)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent or version {version} not found")
    return {"status": "rolled_back", "version": version}

