from __future__ import annotations

from datetime import datetime
from typing import Any, Annotated, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from core.api.utils.run_contract import wrap_execution_result_as_run_summary
from core.apps.tools.permission import Permission, get_permission_manager
from core.harness.integration import KernelRuntime, get_harness
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.kernel.types import ExecutionRequest
from core.services.trace_service import SpanStatus

router = APIRouter()

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]


def _store(rt: Optional[KernelRuntime]):
    return getattr(rt, "execution_store", None) if rt else None


def _trace_service(rt: Optional[KernelRuntime]):
    return getattr(rt, "trace_service", None) if rt else None


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


# ==================== Trace / Graph Persistence ====================


@router.get("/traces")
async def list_traces(limit: int = 100, offset: int = 0, status: Optional[str] = None, rt: RuntimeDep = None):
    """List persisted traces (requires ExecutionStore)."""
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    items, total = await store.list_traces(limit=limit, offset=offset, status=status)
    traces = [
        {
            **t,
            "start_time": datetime.utcfromtimestamp(t["start_time"]).isoformat() if t.get("start_time") else None,
            "end_time": datetime.utcfromtimestamp(t["end_time"]).isoformat() if t.get("end_time") else None,
        }
        for t in items
    ]
    return {"traces": traces, "total": total, "limit": limit, "offset": offset}


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str, rt: RuntimeDep = None):
    """Get a persisted trace with spans."""
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    trace = await store.get_trace(trace_id, include_spans=True)
    if not trace:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    trace["start_time"] = datetime.utcfromtimestamp(trace["start_time"]).isoformat() if trace.get("start_time") else None
    trace["end_time"] = datetime.utcfromtimestamp(trace["end_time"]).isoformat() if trace.get("end_time") else None
    for s in trace.get("spans", []) or []:
        s["start_time"] = datetime.utcfromtimestamp(s["start_time"]).isoformat() if s.get("start_time") else None
        s["end_time"] = datetime.utcfromtimestamp(s["end_time"]).isoformat() if s.get("end_time") else None
    return trace


@router.get("/traces/{trace_id}/executions")
async def list_executions_by_trace(trace_id: str, limit: int = 100, offset: int = 0, rt: RuntimeDep = None):
    """List agent/skill executions linked to a trace_id."""
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    items = await store.list_executions_by_trace_id(trace_id, limit=limit, offset=offset)
    return {"trace_id": trace_id, "items": items, "limit": limit, "offset": offset}


@router.get("/graphs/runs/{run_id}")
async def get_graph_run(run_id: str, rt: RuntimeDep = None):
    """Get a persisted LangGraph run (requires ExecutionStore)."""
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    run = await store.get_graph_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Graph run {run_id} not found")
    run["start_time"] = datetime.utcfromtimestamp(run["start_time"]).isoformat() if run.get("start_time") else None
    run["end_time"] = datetime.utcfromtimestamp(run["end_time"]).isoformat() if run.get("end_time") else None
    return run


@router.get("/graphs/runs")
async def list_graph_runs(
    limit: int = 100,
    offset: int = 0,
    graph_name: Optional[str] = None,
    status: Optional[str] = None,
    trace_id: Optional[str] = None,
    rt: RuntimeDep = None,
):
    """List persisted graph runs (requires ExecutionStore)."""
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    result = await store.list_graph_runs(limit=limit, offset=offset, graph_name=graph_name, status=status, trace_id=trace_id)
    items = result.get("items", [])
    for r in items:
        r["start_time"] = datetime.utcfromtimestamp(r["start_time"]).isoformat() if r.get("start_time") else None
        r["end_time"] = datetime.utcfromtimestamp(r["end_time"]).isoformat() if r.get("end_time") else None
    return {"runs": items, "total": result.get("total", 0), "limit": limit, "offset": offset}


@router.get("/graphs/runs/{run_id}/checkpoints")
async def list_graph_checkpoints(run_id: str, limit: int = 100, offset: int = 0, rt: RuntimeDep = None):
    """List persisted checkpoints for a run."""
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    checkpoints = await store.list_graph_checkpoints(run_id, limit=limit, offset=offset)
    for c in checkpoints:
        c["created_at"] = datetime.utcfromtimestamp(c["created_at"]).isoformat() if c.get("created_at") else None
    return {"run_id": run_id, "checkpoints": checkpoints, "limit": limit, "offset": offset}


@router.get("/graphs/runs/{run_id}/checkpoints/{checkpoint_id}")
async def get_graph_checkpoint(run_id: str, checkpoint_id: str, rt: RuntimeDep = None):
    """Get a persisted checkpoint by id."""
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    ckpt = await store.get_graph_checkpoint(checkpoint_id)
    if not ckpt or ckpt.get("run_id") != run_id:
        raise HTTPException(status_code=404, detail=f"Checkpoint {checkpoint_id} not found")
    ckpt["created_at"] = datetime.utcfromtimestamp(ckpt["created_at"]).isoformat() if ckpt.get("created_at") else None
    return ckpt


@router.post("/graphs/runs/{run_id}/resume")
async def resume_graph_run(run_id: str, request: dict, rt: RuntimeDep = None):
    """
    Create a new run from a checkpoint state (restore/resume semantics).
    request:
      - checkpoint_id (optional)
      - step (optional)
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    user_id = request.get("user_id", "system")
    if user_id != "system":
        perm_mgr = get_permission_manager()
        parent = await store.get_graph_run(run_id)
        graph_name = parent.get("graph_name") if parent else None
        resource_id = f"graph:{graph_name}" if graph_name else f"graph_run:{run_id}"
        if not perm_mgr.check_permission(user_id, resource_id, Permission.EXECUTE):
            raise HTTPException(status_code=403, detail=f"User '{user_id}' lacks EXECUTE permission for '{resource_id}'")

    checkpoint_id = request.get("checkpoint_id")
    step = request.get("step")

    ckpt = None
    if checkpoint_id:
        ckpt = await store.get_graph_checkpoint(checkpoint_id)
    elif step is not None:
        ckpt = await store.get_graph_checkpoint_by_step(run_id, int(step))
    else:
        ckpt = await store.get_latest_graph_checkpoint(run_id)

    if not ckpt:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    if ckpt.get("run_id") != run_id:
        raise HTTPException(status_code=400, detail="Checkpoint does not belong to run_id")

    resumed = await store.resume_graph_run(parent_run_id=run_id, checkpoint_id=ckpt["checkpoint_id"])
    if not resumed:
        raise HTTPException(status_code=500, detail="Failed to resume graph run")
    return resumed


@router.post("/graphs/compiled/react/execute")
async def execute_compiled_react_graph(request: dict, http_request: Request):
    """
    Execute internal CompiledGraph-based ReAct workflow (checkpoint/callback enabled).

    request:
      - messages: [{role, content}]
      - context: dict
      - max_steps: int
      - checkpoint_interval: int
    """
    payload = _inject_http_request_context(dict(request or {}), http_request, entrypoint="api")
    ctx0 = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    user_id = payload.get("user_id") or (ctx0.get("actor_id") if isinstance(ctx0, dict) else None) or "system"
    session_id = payload.get("session_id") or (ctx0.get("session_id") if isinstance(ctx0, dict) else None) or "default"
    exec_req = ExecutionRequest(kind="graph", target_id="compiled_react", payload=payload, user_id=str(user_id), session_id=str(session_id))
    result = await get_harness().execute(exec_req)
    resp = wrap_execution_result_as_run_summary(result)
    return JSONResponse(status_code=200 if resp.get("ok") else int(getattr(result, "http_status", 500) or 500), content=resp)


@router.post("/graphs/runs/{run_id}/resume/execute")
async def resume_and_execute_compiled_graph(run_id: str, request: dict, rt: RuntimeDep = None):
    """
    Resume from a checkpoint and continue executing using CompiledGraph-based ReAct workflow.
    This endpoint closes the loop: resume -> execute -> persist.

    request:
      - checkpoint_id (optional)
      - step (optional)
      - max_steps (optional)
      - checkpoint_interval (optional)
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    user_id = request.get("user_id", "system")
    if user_id != "system":
        perm_mgr = get_permission_manager()
        parent = await store.get_graph_run(run_id)
        graph_name = parent.get("graph_name") if parent else None
        resource_id = f"graph:{graph_name}" if graph_name else f"graph_run:{run_id}"
        if not perm_mgr.check_permission(user_id, resource_id, Permission.EXECUTE):
            raise HTTPException(status_code=403, detail=f"User '{user_id}' lacks EXECUTE permission for '{resource_id}'")

    checkpoint_id = request.get("checkpoint_id")
    step = request.get("step")
    max_steps = int(request.get("max_steps", 10) or 10)
    checkpoint_interval = int(request.get("checkpoint_interval", 1) or 1)

    ckpt = None
    if checkpoint_id:
        ckpt = await store.get_graph_checkpoint(checkpoint_id)
    elif step is not None:
        ckpt = await store.get_graph_checkpoint_by_step(run_id, int(step))
    else:
        ckpt = await store.get_latest_graph_checkpoint(run_id)

    if not ckpt:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    if ckpt.get("run_id") != run_id:
        raise HTTPException(status_code=400, detail="Checkpoint does not belong to run_id")

    resumed = await store.resume_graph_run(parent_run_id=run_id, checkpoint_id=ckpt["checkpoint_id"])
    if not resumed:
        raise HTTPException(status_code=500, detail="Failed to resume graph run")

    restored_state = resumed.get("state") if isinstance(resumed.get("state"), dict) else {}
    restored_state["max_steps"] = max_steps

    class _DefaultModel:
        async def generate(self, prompt):
            return type("R", (), {"content": "DONE"})

    from core.harness.execution.langgraph.compiled_graphs import create_compiled_react_graph
    from core.harness.execution.langgraph.core import GraphConfig

    # attach trace_id for correlation: run_id -> trace_id, and tool spans -> trace_id
    trace_id = None
    ts = _trace_service(rt)
    if ts:
        try:
            t = await ts.start_trace(
                name=f"graph:{resumed.get('graph_name') or 'compiled_react'}",
                attributes={
                    "graph_name": resumed.get("graph_name") or "compiled_react",
                    "graph_run_id": resumed.get("run_id"),
                    "parent_run_id": run_id,
                    "source": "graph",
                },
            )
            trace_id = t.trace_id
        except Exception:
            trace_id = None
    try:
        meta = restored_state.get("metadata") if isinstance(restored_state.get("metadata"), dict) else {}
        meta["trace_id"] = trace_id
        restored_state["metadata"] = meta
    except Exception:
        pass

    graph = create_compiled_react_graph(model=_DefaultModel(), tools=[], max_steps=max_steps, graph_name=resumed.get("graph_name") or "compiled_react")
    try:
        final_state = await graph.execute(
            restored_state,
            config=GraphConfig(max_steps=max_steps, enable_checkpoints=True, checkpoint_interval=checkpoint_interval, enable_callbacks=True),
        )
    finally:
        if ts and trace_id:
            try:
                await ts.end_trace(trace_id, status=SpanStatus.SUCCESS)
            except Exception:
                pass
            try:
                ts._context = None
            except Exception:
                pass
    return {"parent_run_id": run_id, "run_id": resumed.get("run_id"), "checkpoint_id": resumed.get("checkpoint_id"), "final_state": final_state}

