from __future__ import annotations

import time
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

# Legacy in-memory fallback for dev-mode / no ExecutionStore scenarios.
_workspace_agent_history: Dict[str, List[Dict[str, Any]]] = {}


def _store(rt: Optional[KernelRuntime]):
    return getattr(rt, "execution_store", None) if rt else None


def _ws_agent_mgr(rt: Optional[KernelRuntime]):
    return getattr(rt, "workspace_agent_manager", None) if rt else None


def _job_scheduler(rt: Optional[KernelRuntime]):
    return getattr(rt, "job_scheduler", None) if rt else None


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


def _is_verified(meta: Dict[str, Any] | None) -> bool:
    if not isinstance(meta, dict):
        return False
    v = meta.get("verification")
    if isinstance(v, dict):
        return str(v.get("status") or "") == "verified"
    return False


def _autosmoke_gate_error(*, message: str) -> Dict[str, Any]:
    return gate_error_envelope(
        code="agent_unverified",
        message=message,
        next_actions=[{"type": "open_smoke", "label": "打开 Smoke", "url": ui_url("/diagnostics/smoke")}],
    )


# ==================== Workspace Agent Management ====================


@router.get("/workspace/agents")
async def list_workspace_agents(
    agent_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    rt: RuntimeDep = None,
):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        return {"agents": [], "total": 0, "limit": limit, "offset": offset}
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


@router.post("/workspace/agents")
async def create_workspace_agent(request: AgentCreateRequest, http_request: Request, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    try:
        agent = await mgr.create_agent(
            name=request.name,
            agent_type=request.agent_type,
            config=request.config,
            skills=request.skills,
            tools=request.tools,
            memory_config=request.memory_config,
            metadata=request.metadata,
        )
        # Mark as pending verification (best-effort)
        try:
            await mgr.update_agent(
                str(agent.id),
                metadata={"verification": {"status": "pending", "updated_at": time.time(), "source": "autosmoke"}},
            )
        except Exception:
            pass

        # Auto-smoke (async, dedup): trigger on create/update to validate the full chain.
        try:
            store = _store(rt)
            sched = _job_scheduler(rt)
            if store is not None and sched is not None:
                from core.harness.smoke import enqueue_autosmoke

                tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
                actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")
                agent_id = str(agent.id)

                async def _on_complete(job_run: Dict[str, Any]):
                    st = str(job_run.get("status") or "")
                    ver = {
                        "status": "verified" if st == "completed" else "failed",
                        "updated_at": time.time(),
                        "source": "autosmoke",
                        "job_id": f"autosmoke-agent:{agent_id}",
                        "job_run_id": str(job_run.get("id") or ""),
                        "reason": str(job_run.get("error") or ""),
                    }
                    try:
                        await mgr.update_agent(agent_id, metadata={"verification": ver})
                    except Exception:
                        pass

                await enqueue_autosmoke(
                    execution_store=store,
                    job_scheduler=sched,
                    resource_type="agent",
                    resource_id=agent_id,
                    tenant_id=tenant_id or "ops_smoke",
                    actor_id=actor_id or "admin",
                    detail={"op": "create", "name": agent.name},
                    on_complete=_on_complete,
                )
        except Exception:
            pass

        return {"id": agent.id, "status": "created", "name": agent.name}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/workspace/agents/{agent_id}")
async def get_workspace_agent(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
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
        "memory_config": agent.memory_config,
        "metadata": agent.metadata,
    }


@router.get("/workspace/agents/{agent_id}/sop")
async def get_workspace_agent_sop(agent_id: str, rt: RuntimeDep = None):
    """Get agent SOP (markdown) from AGENT.md '## SOP' section."""
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    data = await mgr.get_agent_sop(agent_id)  # type: ignore[attr-defined]
    if not data:
        raise HTTPException(status_code=404, detail="SOP not found")
    return data


@router.put("/workspace/agents/{agent_id}/sop")
async def update_workspace_agent_sop(agent_id: str, request: dict, rt: RuntimeDep = None):
    """Update agent SOP section in AGENT.md."""
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    sop = (request or {}).get("sop")
    if sop is None:
        raise HTTPException(status_code=400, detail="Missing field: sop")
    try:
        ok = await mgr.update_agent_sop(agent_id, str(sop))  # type: ignore[attr-defined]
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to update SOP")
    return {"status": "updated", "id": agent_id}


@router.get("/workspace/agents/{agent_id}/execution-help")
async def get_workspace_agent_execution_help(agent_id: str, rt: RuntimeDep = None):
    """Get execution input help/examples for agent."""
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    data = await mgr.get_agent_execution_help(agent_id)  # type: ignore[attr-defined]
    if not data:
        raise HTTPException(status_code=404, detail="Execution help not found")
    return data


@router.delete("/workspace/agents/{agent_id}")
async def delete_workspace_agent(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    ok = await mgr.delete_agent(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "deleted", "id": agent_id}


@router.post("/workspace/agents/{agent_id}/start")
async def start_workspace_agent(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    try:
        from core.governance.gating import autosmoke_enforce
    except Exception:
        autosmoke_enforce = None  # type: ignore

    if autosmoke_enforce and autosmoke_enforce(store=_store(rt)):
        a = await mgr.get_agent(agent_id)
        if not a:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        if not _is_verified(getattr(a, "metadata", None)):
            raise HTTPException(status_code=403, detail=_autosmoke_gate_error(message="smoke must pass before start"))
    ok = await mgr.start_agent(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "started", "id": agent_id}


@router.post("/workspace/agents/{agent_id}/stop")
async def stop_workspace_agent(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    ok = await mgr.stop_agent(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "stopped", "id": agent_id}


@router.put("/workspace/agents/{agent_id}")
async def update_workspace_agent(agent_id: str, request: AgentUpdateRequest, http_request: Request, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.update_agent(
        agent_id,
        name=request.name,
        config=request.config,
        skills=request.skills,
        tools=request.tools,
        memory_config=request.memory_config,
        metadata=request.metadata,
    )
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    # Mark as pending verification (best-effort)
    try:
        await mgr.update_agent(str(agent_id), metadata={"verification": {"status": "pending", "updated_at": time.time(), "source": "autosmoke"}})
    except Exception:
        pass

    # Auto-smoke (async, dedup)
    try:
        store = _store(rt)
        sched = _job_scheduler(rt)
        if store is not None and sched is not None:
            from core.harness.smoke import enqueue_autosmoke

            tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
            actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")
            aid = str(agent_id)

            async def _on_complete(job_run: Dict[str, Any]):
                st = str(job_run.get("status") or "")
                ver = {
                    "status": "verified" if st == "completed" else "failed",
                    "updated_at": time.time(),
                    "source": "autosmoke",
                    "job_id": f"autosmoke-agent:{aid}",
                    "job_run_id": str(job_run.get("id") or ""),
                    "reason": str(job_run.get("error") or ""),
                }
                try:
                    await mgr.update_agent(aid, metadata={"verification": ver})
                except Exception:
                    pass

            await enqueue_autosmoke(
                execution_store=store,
                job_scheduler=sched,
                resource_type="agent",
                resource_id=aid,
                tenant_id=tenant_id or "ops_smoke",
                actor_id=actor_id or "admin",
                detail={"op": "update"},
                on_complete=_on_complete,
            )
    except Exception:
        pass
    return {"status": "updated", "id": agent_id}


# ==================== skills/tools bindings ====================


@router.get("/workspace/agents/{agent_id}/skills")
async def get_workspace_agent_skills(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
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


@router.post("/workspace/agents/{agent_id}/skills")
async def bind_workspace_agent_skills(agent_id: str, request: dict, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    skill_ids = (request or {}).get("skill_ids", [])
    if skill_ids:
        await mgr.bind_skills(agent_id, skill_ids)
    return {"status": "bound", "skill_ids": skill_ids}


@router.delete("/workspace/agents/{agent_id}/skills/{skill_id}")
async def unbind_workspace_agent_skill(agent_id: str, skill_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    await mgr.unbind_skill(agent_id, skill_id)
    return {"status": "unbound"}


@router.get("/workspace/agents/{agent_id}/tools")
async def get_workspace_agent_tools(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
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


@router.post("/workspace/agents/{agent_id}/tools")
async def bind_workspace_agent_tools(agent_id: str, request: dict, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    tool_ids = (request or {}).get("tool_ids", [])
    if tool_ids:
        await mgr.bind_tools(agent_id, tool_ids)
    return {"status": "bound", "tool_ids": tool_ids}


@router.delete("/workspace/agents/{agent_id}/tools/{tool_id}")
async def unbind_workspace_agent_tool(agent_id: str, tool_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    await mgr.unbind_tool(agent_id, tool_id)
    return {"status": "unbound"}


# ==================== execute / history / versions ====================


@router.post("/workspace/agents/{agent_id}/execute")
async def execute_workspace_agent(agent_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    payload = _inject_http_request_context(dict(request or {}), http_request, entrypoint="api")
    deny = await rbac_guard(http_request=http_request, payload=payload, action="execute", resource_type="agent", resource_id=str(agent_id))
    if deny:
        return deny

    # autosmoke verified gate (graded): block execute when enforce is enabled and agent is not verified.
    try:
        from core.governance.gating import autosmoke_enforce
    except Exception:
        autosmoke_enforce = None  # type: ignore

    if autosmoke_enforce and autosmoke_enforce(store=_store(rt)):
        if not _is_verified(getattr(agent, "metadata", None)):
            raise HTTPException(status_code=403, detail=_autosmoke_gate_error(message="smoke must pass before execute"))

    ctx0 = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    user_id = payload.get("user_id") or (ctx0.get("actor_id") if isinstance(ctx0, dict) else None) or "system"
    session_id = payload.get("session_id") or (ctx0.get("session_id") if isinstance(ctx0, dict) else None) or "default"

    exec_req = ExecutionRequest(kind="agent", target_id=agent_id, payload=payload, user_id=str(user_id), session_id=str(session_id))
    result = await get_harness().execute(exec_req)
    resp = wrap_execution_result_as_run_summary(result)
    try:
        await _audit_execute(rt, http_request=http_request, payload=payload, resource_type="agent", resource_id=str(agent_id), resp=resp)
    except Exception:
        pass
    return JSONResponse(status_code=200 if resp.get("ok") else int(getattr(result, "http_status", 500) or 500), content=resp)


@router.get("/workspace/agents/{agent_id}/history")
async def get_workspace_agent_history(agent_id: str, limit: int = 100, offset: int = 0, rt: RuntimeDep = None):
    store = _store(rt)
    if store:
        history, total = await store.list_agent_history(agent_id, limit=limit, offset=offset)
        return {"history": history, "total": total}
    history = _workspace_agent_history.get(agent_id, [])[offset : offset + limit]
    return {"history": history, "total": len(_workspace_agent_history.get(agent_id, []))}


@router.get("/workspace/agents/{agent_id}/versions")
async def get_workspace_agent_versions(agent_id: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    versions = await mgr.get_versions(agent_id)
    return {"agent_id": agent_id, "versions": [{"version": v.version, "status": v.status, "created_at": v.created_at.isoformat(), "changes": v.changes} for v in versions]}


@router.post("/workspace/agents/{agent_id}/versions")
async def create_workspace_agent_version(agent_id: str, request: dict, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    changes = (request or {}).get("changes", "")
    version = await mgr.create_version(agent_id, changes)
    if not version:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"version": version.version, "status": version.status, "created_at": version.created_at.isoformat(), "changes": version.changes}


@router.post("/workspace/agents/{agent_id}/versions/{version}/rollback")
async def rollback_workspace_agent_version(agent_id: str, version: str, rt: RuntimeDep = None):
    mgr = _ws_agent_mgr(rt)
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    ok = await mgr.rollback_version(agent_id, version)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent or version {version} not found")
    return {"status": "rolled_back", "version": version}

