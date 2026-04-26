from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from core.api.deps.rbac import actor_from_http
from core.api.utils.governance import ui_url
from core.governance.verification import apply_autosmoke_result, autosmoke_job_id, get_resource_verification, mark_resource_pending
from core.harness.kernel.runtime import get_kernel_runtime


router = APIRouter()


def _store():
    rt = get_kernel_runtime()
    return getattr(rt, "execution_store", None) if rt else None


def _job_scheduler():
    rt = get_kernel_runtime()
    return getattr(rt, "job_scheduler", None) if rt else None


def _autosmoke_job_id(resource_type: str, resource_id: str) -> str:
    return autosmoke_job_id(resource_type, resource_id)


def _workspace_managers():
    rt = get_kernel_runtime()
    return (
        getattr(rt, "workspace_agent_manager", None) if rt else None,
        getattr(rt, "workspace_skill_manager", None) if rt else None,
        getattr(rt, "workspace_mcp_manager", None) if rt else None,
    )


@router.post("/autosmoke/run")
async def run_autosmoke(request: Dict[str, Any], http_request: Request):
    """
    Productized wrapper: enqueue autosmoke for a resource and persist verification state updates.
    """
    store = _store()
    scheduler = _job_scheduler()
    if not store or not scheduler:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rtype = str((request or {}).get("resource_type") or "").strip().lower()
    rid = str((request or {}).get("resource_id") or "").strip()
    if not rtype or not rid:
        raise HTTPException(status_code=400, detail="resource_type/resource_id required")
    actor0 = actor_from_http(http_request, request if isinstance(request, dict) else None)
    tenant_id = str((request or {}).get("tenant_id") or actor0.get("tenant_id") or "ops_smoke")
    actor_id = str((request or {}).get("actor_id") or actor0.get("actor_id") or "admin")
    detail = (request or {}).get("detail") if isinstance((request or {}).get("detail"), dict) else {}

    wam, wsm, wmm = _workspace_managers()
    try:
        await mark_resource_pending(resource_type=rtype, resource_id=rid, workspace_agent_manager=wam, workspace_skill_manager=wsm, workspace_mcp_manager=wmm)
    except Exception:
        pass

    from core.harness.smoke import enqueue_autosmoke

    async def _on_complete(job_run: Dict[str, Any]):
        await apply_autosmoke_result(
            resource_type=rtype,
            resource_id=rid,
            job_run=job_run,
            workspace_agent_manager=wam,
            workspace_skill_manager=wsm,
            workspace_mcp_manager=wmm,
        )

    res = await enqueue_autosmoke(
        execution_store=store,
        job_scheduler=scheduler,
        resource_type=rtype,
        resource_id=rid,
        tenant_id=tenant_id,
        actor_id=actor_id,
        detail={"op": "manual_run", **(detail or {})},
        on_complete=_on_complete,
    )
    # Enrich response with links
    try:
        jid = res.get("job_id") or autosmoke_job_id(rtype, rid)
        res["links"] = {
            "jobs_ui": ui_url("/core/jobs"),
            "job_runs_ui": ui_url(f"/core/jobs?job_id={jid}"),
            "syscalls_ui": ui_url("/diagnostics/syscalls?kind=onboarding&target_type=onboarding_evidence&target_id="),
        }
    except Exception:
        pass
    return res


@router.get("/autosmoke/runs")
async def list_autosmoke_runs(resource_type: str, resource_id: str, http_request: Request, limit: int = 50, offset: int = 0):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rtype = str(resource_type or "").strip().lower()
    rid = str(resource_id or "").strip()
    if not rtype or not rid:
        raise HTTPException(status_code=400, detail="resource_type/resource_id required")
    job_id = _autosmoke_job_id(rtype, rid)
    runs = await store.list_job_runs(job_id=job_id, limit=limit, offset=offset)
    # Attach UI links for convenience
    items = []
    for it in runs.get("items") or []:
        d = dict(it)
        try:
            run_id = str(d.get("id") or "")
            d["links"] = {
                "run_ui": ui_url(f"/diagnostics/runs?run_id={run_id}"),
                "syscalls_ui": ui_url(f"/diagnostics/syscalls?run_id={run_id}"),
                "audit_ui": ui_url(f"/diagnostics/audit?action=autosmoke_result&resource_id={rid}"),
            }
        except Exception:
            pass
        items.append(d)
    return {**runs, "job_id": job_id, "resource": {"type": rtype, "id": rid}, "items": items}


@router.get("/autosmoke/status")
async def get_autosmoke_status(resource_type: str, resource_id: str, http_request: Request):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    rtype = str(resource_type or "").strip().lower()
    rid = str(resource_id or "").strip()
    if not rtype or not rid:
        raise HTTPException(status_code=400, detail="resource_type/resource_id required")
    job_id = _autosmoke_job_id(rtype, rid)
    latest = await store.list_job_runs(job_id=job_id, limit=1, offset=0)
    latest_run = (latest.get("items") or [None])[0]
    wam, wsm, wmm = _workspace_managers()
    verification = await get_resource_verification(
        resource_type=rtype,
        resource_id=rid,
        workspace_agent_manager=wam,
        workspace_skill_manager=wsm,
        workspace_mcp_manager=wmm,
    )
    return {"resource": {"type": rtype, "id": rid}, "job_id": job_id, "latest_run": latest_run, "verification": verification}
