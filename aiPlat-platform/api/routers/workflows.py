"""
Workflow API router — CRUD + execute for workflow definitions.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from auth.deps import require_auth
from builder.builder_workflow_service import WorkflowService

router = APIRouter(prefix="/platform/workflows", tags=["workflows"])
_svc = WorkflowService()
_log = logging.getLogger(__name__)


def _get_wf_mgr():
    try:
        from core.management.workflow_manager import WorkflowManager
        return WorkflowManager(scope="workspace")
    except Exception:
        return None


async def _record_workflow_changeset(name: str, workflow_id: str, status: str = "success", args: dict = None, error: str = None):
    """Best-effort: record a workflow mutation as a changeset for audit."""
    try:
        from core.api.core_facade import record_changeset
        await record_changeset(
            name=name,
            target_type="workflow",
            target_id=workflow_id,
            status=status,
            args=args or {},
            error=error,
            user_id="admin",
        )
    except Exception:
        _log.debug(f"Failed to record changeset for workflow {workflow_id}", exc_info=True)


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
        await _record_workflow_changeset("create_workflow", item["id"], args={"name": item.get("name", "")})
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
        await _record_workflow_changeset("update_workflow", workflow_id, args=kwargs)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{workflow_id}")
async def delete_workflow_endpoint(workflow_id: str, _auth: str = Depends(require_auth)):
    await _svc.delete(workflow_id)
    await _record_workflow_changeset("delete_workflow", workflow_id)
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
    # Try directory-based manager first, fall back to SQLite
    mgr = _get_wf_mgr()
    if mgr:
        result = mgr.toggle_enabled(workflow_id)
        if result is None:
            raise HTTPException(status_code=404, detail="workflow not found")
        await _record_workflow_changeset("toggle_workflow", workflow_id, args={"enabled": result})
        return {"enabled": result, "workflow_id": workflow_id}

    from storage.sqlite import toggle_workflow_enabled
    result = toggle_workflow_enabled(workflow_id)
    if result is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    await _record_workflow_changeset("toggle_workflow", workflow_id, args={"enabled": result})
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


@router.post("/{workflow_id}/sign")
async def sign_workflow(workflow_id: str, req: Dict[str, Any] = {}, _auth: str = Depends(require_auth)):
    """Sign a workflow directory with an Ed25519 private key. Writes WORKFLOW.manifest.json."""
    mgr = _get_wf_mgr()
    if not mgr:
        raise HTTPException(status_code=503, detail="Workflow manager not available (not migrated to directory storage yet)")

    wf = mgr.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="workflow not found")

    private_key = str(req.get("private_key") or "").strip()
    private_key = private_key.replace("\\n", "\n")  # normalize escaped newlines from frontend
    if not private_key:
        raise HTTPException(status_code=400, detail="private_key is required")

    try:
        from core.harness.infrastructure.crypto.signature import sign_skill as sign_wf

        wf_dir = Path(wf.metadata.get("filesystem", {}).get("server_dir") or "")
        if not wf_dir or not wf_dir.exists():
            raise HTTPException(status_code=500, detail="Workflow directory not found")

        mgr._enrich_workflow_provenance_and_integrity(wf.metadata, workflow_dir=wf_dir)
        integ = wf.metadata.get("integrity", {})
        bundle_sha256 = integ.get("bundle_sha256", "")
        if not bundle_sha256:
            raise HTTPException(status_code=500, detail="Could not compute bundle_sha256")

        version = req.get("version") or wf.version or "0.1.0"
        signature = sign_wf(private_key=private_key, skill_id=workflow_id, version=str(version), bundle_sha256=bundle_sha256)

        manifest_path = wf_dir / "WORKFLOW.manifest.json"
        manifest = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        manifest["signature"] = signature
        manifest["version"] = str(version)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        mgr._enrich_workflow_provenance_and_integrity(wf.metadata, workflow_dir=wf_dir)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid private key: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Signing failed: {str(e)}")

    return {"status": "signed", "bundle_sha256": bundle_sha256, "version": str(version), "signature": signature}


@router.post("/{workflow_id}/publish")
async def publish_version_endpoint(workflow_id: str, req: Dict[str, Any] = {}, _auth: str = Depends(require_auth)):
    # Try directory-based manager first
    mgr = _get_wf_mgr()
    if mgr:
        ver = mgr.publish(workflow_id)
        await _record_workflow_changeset("publish_workflow", workflow_id, args={"version": ver.get("status")})
        return ver

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
    await _record_workflow_changeset("publish_workflow", workflow_id, args={"version": ver.get("version")})
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
