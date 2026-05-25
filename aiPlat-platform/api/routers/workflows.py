"""
Workflow API router — CRUD + execute for workflow definitions.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from auth.deps import require_auth
from builder.builder_workflow_service import WorkflowService

router = APIRouter(prefix="/platform/workflows", tags=["workflows"])
_svc = WorkflowService()


@router.get("")
async def list_workflows_endpoint(_auth: str = Depends(require_auth)):
    items = await _svc.list()
    return {"workflows": items, "total": len(items)}


@router.get("/{workflow_id}")
async def get_workflow_endpoint(workflow_id: str, _auth: str = Depends(require_auth)):
    item = await _svc.get(workflow_id)
    if not item:
        raise HTTPException(status_code=404, detail="workflow not found")
    return item


@router.post("")
async def create_workflow_endpoint(req: Dict[str, Any], _auth: str = Depends(require_auth)):
    try:
        item = await _svc.create(
            name=str(req.get("name") or "未命名工作流"),
            description=str(req.get("description") or ""),
            nodes=req.get("nodes") or [],
            edges=req.get("edges") or [],
        )
        return item
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{workflow_id}")
async def update_workflow_endpoint(workflow_id: str, req: Dict[str, Any], _auth: str = Depends(require_auth)):
    kwargs: Dict[str, Any] = {}
    if "name" in req:
        kwargs["name"] = str(req["name"])
    if "description" in req:
        kwargs["description"] = str(req["description"])
    if "nodes" in req:
        kwargs["nodes"] = req["nodes"]
    if "edges" in req:
        kwargs["edges"] = req["edges"]
    try:
        result = await _svc.update(workflow_id, **kwargs)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{workflow_id}")
async def delete_workflow_endpoint(workflow_id: str, _auth: str = Depends(require_auth)):
    await _svc.delete(workflow_id)
    return {"status": "deleted", "id": workflow_id}


@router.post("/{workflow_id}/execute")
async def execute_workflow_endpoint(workflow_id: str, req: Dict[str, Any] = {}, _auth: str = Depends(require_auth)):
    try:
        result = await _svc.execute(workflow_id, launch_name=str(req.get("name") or ""))
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{workflow_id}/runs")
async def list_workflow_runs_endpoint(workflow_id: str, _auth: str = Depends(require_auth)):
    runs = await _svc.list_runs(workflow_id)
    return {"runs": runs, "total": len(runs)}


@router.post("/{workflow_id}/toggle-enabled")
async def toggle_workflow_enabled_endpoint(workflow_id: str, _auth: str = Depends(require_auth)):
    from storage.sqlite import toggle_workflow_enabled
    result = toggle_workflow_enabled(workflow_id)
    if result is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return {"enabled": result, "workflow_id": workflow_id}


@router.get("/runs/{run_id}/events/latest")
async def get_latest_event_endpoint(run_id: str, _auth: str = Depends(require_auth)):
    from storage.sqlite import get_latest_event
    event = get_latest_event(run_id)
    if not event:
        return {"event": None}
    return {"event": event}


@router.get("/runs/{run_id}/events")
async def list_events_endpoint(run_id: str, _auth: str = Depends(require_auth)):
    from storage.sqlite import list_pipeline_events
    events = list_pipeline_events(run_id)
    return {"events": events, "total": len(events)}


@router.post("/{workflow_id}/stop")
async def stop_workflow_run(workflow_id: str, req: Dict[str, Any] = {}, _auth: str = Depends(require_auth)):
    """Cancel a running pipeline by project_id."""
    project_id = str(req.get("project_id", ""))
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")
    from core.api.core_facade import cancel_pipeline
    cancel_pipeline(project_id)
    return {"status": "cancelled", "project_id": project_id}


@router.post("/{workflow_id}/publish")
async def publish_version_endpoint(workflow_id: str, req: Dict[str, Any] = {}, _auth: str = Depends(require_auth)):
    from storage.sqlite import get_workflow, publish_workflow_version
    wf = get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="workflow not found")
    ver = publish_workflow_version(
        workflow_id,
        name=str(req.get("name") or wf.get("name", "")),
        nodes=wf.get("nodes") or [],
        edges=wf.get("edges") or [],
    )
    return ver


@router.get("/{workflow_id}/versions")
async def list_versions_endpoint(workflow_id: str, _auth: str = Depends(require_auth)):
    from storage.sqlite import list_workflow_versions
    versions = list_workflow_versions(workflow_id)
    return {"versions": versions, "total": len(versions), "latest_version": versions[0]["version"] if versions else 0}


@router.post("/{workflow_id}/restore/{version_id:path}")
async def restore_version_endpoint(workflow_id: str, version_id: str, _auth: str = Depends(require_auth)):
    from storage.sqlite import get_workflow_version, update_workflow
    ver = get_workflow_version(version_id)
    if not ver:
        raise HTTPException(status_code=404, detail="version not found")
    result = update_workflow(workflow_id, nodes=ver.get("nodes"), edges=ver.get("edges"))
    if not result:
        raise HTTPException(status_code=404, detail="workflow not found")
    return {"status": "restored", "from_version": ver["version"]}
