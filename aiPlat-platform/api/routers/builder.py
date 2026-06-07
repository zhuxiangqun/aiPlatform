"""
Builder API router — backed by platform-local builder services.
Each endpoint proxies to the local Builder service with proper type deserialization.
"""
from __future__ import annotations

import json as _json
import logging
import os
from typing import Any, Dict, List
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from builder.builder_project_service import BuilderProjectService

_log = logging.getLogger(__name__)
from builder.builder_team_service import BuilderTeamService
from builder.builder_auth import require_builder_access, require_admin_access
from core.schemas_builder import (
    BuilderChatRequest,
    BuilderSessionCreateRequest,
    ProjectCreateRequest,
    TeamAssembleRequest,
)

router = APIRouter(prefix="/platform/builder", tags=["builder"])

_team_svc = BuilderTeamService()
_svc = BuilderProjectService(team_service=_team_svc)

_deprecation_header = {"Deprecation": "true", "Sunset": "Sat, 01 Jan 2027 00:00:00 GMT",
                        "Link": '</api/v2/projects>; rel="successor-version"'}


def _legacy_response(data: dict) -> JSONResponse:
    """Wrap legacy /sessions/ response with deprecation headers."""
    return JSONResponse(content=data, headers=_deprecation_header)


# ---- Sessions (legacy, forward to projects) ----

@router.post("/sessions")
async def create_builder_session(req: BuilderSessionCreateRequest, _auth: str = Depends(require_builder_access)):
    """Legacy: auto-create project from requirement and return session info."""
    proj = await _svc.create_project(ProjectCreateRequest(name=req.requirement[:30] or "新项目", description=req.requirement))
    return _legacy_response({"session_id": proj.project_id, "phase": "dialogue"})

@router.post("/sessions/{session_id}/chat")
async def builder_chat(session_id: str, req: BuilderChatRequest, _auth: str = Depends(require_builder_access)):
    return _legacy_response(await _svc.chat(session_id, req.message))

@router.post("/sessions/{session_id}/confirm")
async def session_confirm(session_id: str, _auth: str = Depends(require_builder_access)):
    return _legacy_response(await _svc.confirm_prd(session_id))

@router.post("/sessions/{session_id}/start")
async def session_start(session_id: str, _auth: str = Depends(require_builder_access)):
    return _legacy_response(await _svc.start_pipeline(session_id))

@router.get("/sessions/{session_id}")
async def get_session(session_id: str, _auth: str = Depends(require_builder_access)):
    return _legacy_response(await _svc.get_project_state(session_id))

# ---- Session HITL (legacy, forward to projects) ----

@router.post("/sessions/{session_id}/approve-architecture")
async def session_approve_architecture(session_id: str, _auth: str = Depends(require_builder_access)):
    return _legacy_response(await _svc.approve_stage(session_id))

@router.post("/sessions/{session_id}/reject-architecture")
async def session_reject_architecture(session_id: str, feedback: str = "", _auth: str = Depends(require_builder_access)):
    return _legacy_response(await _svc.reject_stage(session_id, feedback))

@router.post("/sessions/{session_id}/approve-test-plan")
async def session_approve_test_plan(session_id: str, _auth: str = Depends(require_builder_access)):
    return _legacy_response(await _svc.approve_stage(session_id))

@router.post("/sessions/{session_id}/reject-test-plan")
async def session_reject_test_plan(session_id: str, feedback: str = "", _auth: str = Depends(require_builder_access)):
    return _legacy_response(await _svc.reject_stage(session_id, feedback))


# ---- Projects ----

@router.get("/projects")
async def list_projects(_auth: str = Depends(require_builder_access)):
    projects = await _svc.list_projects()
    result = [p.model_dump() if hasattr(p, 'model_dump') else p for p in projects]
    return {"projects": result, "total": len(result)}

@router.post("/projects")
async def create_project(req: ProjectCreateRequest, _auth: str = Depends(require_admin_access)):
    return await _svc.create_project(req)

@router.get("/projects/{project_id}")
async def get_project(project_id: str, _auth: str = Depends(require_builder_access)):
    return await _svc.get_project(project_id)

@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, _auth: str = Depends(require_admin_access)):
    return await _svc.delete_project(project_id)

@router.get("/projects/{project_id}/state")
async def get_project_state(project_id: str, _auth: str = Depends(require_builder_access)):
    return await _svc.get_project_state(project_id)

@router.post("/projects/{project_id}/chat")
async def project_chat(project_id: str, req: BuilderChatRequest, _auth: str = Depends(require_builder_access)):
    return await _svc.chat(project_id, req.message)

@router.post("/projects/{project_id}/confirm")
async def project_confirm(project_id: str, body: Dict[str, Any] = {}, _auth: str = Depends(require_builder_access)):
    return await _svc.confirm_prd(project_id, prd_data=body.get("prd"))

@router.post("/projects/{project_id}/recommend-team")
async def recommend_team(project_id: str, _auth: str = Depends(require_builder_access)):
    """AI analyzes PRD and recommends a team configuration."""
    return await _svc.recommend_team(project_id)

@router.post("/projects/{project_id}/start")
async def project_start(project_id: str, _auth: str = Depends(require_builder_access)):
    return await _svc.start_pipeline(project_id)

@router.post("/projects/{project_id}/approve")
async def project_approve(project_id: str, _auth: str = Depends(require_builder_access)):
    return await _svc.approve_stage(project_id)

@router.post("/projects/{project_id}/reject")
async def project_reject(project_id: str, body: Dict[str, Any] = {}, _auth: str = Depends(require_builder_access)):
    feedback = str(body.get("feedback", "") or "")
    return await _svc.reject_stage(project_id, feedback)

@router.post("/projects/{project_id}/rollback/{stage_id:path}")
async def project_rollback(project_id: str, stage_id: str, _auth: str = Depends(require_builder_access)):
    return await _svc.rollback_stage(project_id, stage_id)


@router.post("/projects/{project_id}/rollback-prd")
async def project_rollback_prd(project_id: str, _auth: str = Depends(require_builder_access)):
    """Roll back to PRD editing phase — clears pipeline state and confirmed PRD."""
    return await _svc.rollback_prd(project_id)

@router.post("/projects/{project_id}/fix")
async def project_fix(project_id: str, _auth: str = Depends(require_builder_access)):
    return await _svc.start_fix(project_id)

@router.post("/projects/{project_id}/resume/{stage_id:path}")
async def project_resume(project_id: str, stage_id: str, _auth: str = Depends(require_builder_access)):
    """Resume pipeline from a specific stage (rollback without clearing artifacts)."""
    return await _svc.resume_from_stage(project_id, stage_id)

@router.get("/projects/{project_id}/deploy")
async def project_deploy(project_id: str, _auth: str = Depends(require_builder_access)):
    deploy_dir = await _svc.get_deploy_dir(project_id)
    if not deploy_dir:
        raise HTTPException(404, detail="Deploy package not ready. Run pipeline first.")
    return {"project_id": project_id, "deploy_dir": deploy_dir}


# ---- Teams ----

@router.post("/teams")
async def create_team(req: TeamAssembleRequest, _auth: str = Depends(require_builder_access)):
    return await _team_svc.create_team(req)

@router.get("/teams")
async def list_teams(_auth: str = Depends(require_builder_access)):
    teams = await _team_svc.list_teams()
    return {"teams": [t.model_dump() if hasattr(t, 'model_dump') else t for t in teams], "total": len(teams)}

@router.get("/teams/{team_id}")
async def get_team(team_id: str, _auth: str = Depends(require_builder_access)):
    return await _team_svc.get_team(team_id)

@router.put("/teams/{team_id}")
async def update_team(team_id: str, req: TeamAssembleRequest, _auth: str = Depends(require_builder_access)):
    result = await _team_svc.update_team(team_id, req)
    if not result:
        raise HTTPException(404, detail="Team not found")
    return result

@router.delete("/teams/{team_id}")
async def delete_team(team_id: str, _auth: str = Depends(require_admin_access)):
    return await _team_svc.delete_team(team_id)

@router.post("/teams/{team_id}/run")
async def run_team(team_id: str, body: Dict[str, Any], _auth: str = Depends(require_builder_access)):
    return await _team_svc.run_team(team_id, body.get("description", ""))


@router.get("/projects/{project_id}/graph")
async def get_pipeline_graph(project_id: str, _auth: str = Depends(require_builder_access)):
    """Return pipeline execution graph data for visualization."""
    return await _svc.get_graph(project_id)


@router.post("/projects/{project_id}/test")
async def run_project_tests(project_id: str, _auth: str = Depends(require_builder_access)):
    """Run E2E smoke + repo tests for a completed project pipeline."""
    return await _svc.run_tests(project_id)


@router.post("/projects/{project_id}/deploy-to-app")
async def deploy_project_to_app(project_id: str, _auth: str = Depends(require_admin_access)):
    """Deploy pipeline output to the app layer (requires admin approval)."""
    # Verify project signature before deploy
    try:
        proj = _svc._projects.get(project_id)
        if proj and proj.get("metadata", {}).get("provenance", {}).get("signature"):
            import os, json as _json, hashlib as _hashlib
            from core.harness.infrastructure.crypto.signature import verify_skill_signature
            proj_dir = os.path.join(os.environ.get("AIPLAT_HOME", str(Path.home() / ".aiplat")), "projects", project_id)
            manifest_path = os.path.join(proj_dir, "PROJECT.manifest.json")
            proj_json = os.path.join(proj_dir, "project.json")
            if os.path.exists(manifest_path) and os.path.exists(proj_json):
                with open(manifest_path) as f: manifest = _json.load(f)
                h = _hashlib.sha256(); h.update(Path(proj_json).read_bytes())
                sig = manifest.get("signature")
                if sig:
                    r = verify_skill_signature(skill_id=project_id, version=manifest.get("version", "0.1.0"),
                        bundle_sha256=h.hexdigest(), signature=sig, trusted_keys={})
                    if not r.get("verified"):
                        raise HTTPException(status_code=403, detail=f"Project signature verification failed before deploy")
    except HTTPException: raise
    except Exception:
        _log.warning("部署签名验证失败，跳过: project_id=%s", project_id, exc_info=True)
    return await _svc.deploy_to_app(project_id)


@router.get("/agent-insight/{agent_id}")
async def get_agent_insight(agent_id: str, _auth: str = Depends(require_builder_access)):
    """Get insight metrics for a single agent."""
    return await _svc.get_agent_insight(agent_id)


@router.get("/agent-insights")
async def list_agent_insights(_auth: str = Depends(require_builder_access)):
    """Get insight metrics for all agents."""
    return await _svc.list_agent_insights()


@router.post("/agent-insights/refresh")
async def refresh_agent_insights(_auth: str = Depends(require_builder_access)):
    """Refresh agent insight metrics."""
    return await _svc.refresh_agent_insights()


@router.get("/projects/{project_id}/health-report")
async def get_project_health_report(project_id: str, _auth: str = Depends(require_builder_access)):
    """Get pipeline health report with per-stage dimensional scores."""
    return await _svc.get_health_report(project_id)


@router.get("/projects/{project_id}/export")
async def export_project_state(project_id: str, _auth: str = Depends(require_builder_access)):
    """Export full project execution state as downloadable JSON."""
    from fastapi.responses import JSONResponse
    state = await _svc.get_project_state(project_id)
    return JSONResponse(
        content=state,
        headers={"Content-Disposition": f'attachment; filename="aiplat_{project_id}_export.json"'}
    )


@router.post("/projects/{project_id}/sign")
async def sign_project(project_id: str, req: Dict[str, Any], _auth: str = Depends(require_admin_access)):
    """
    Sign a project directory with an Ed25519 private key.
    Writes PROJECT.manifest.json into the project directory.
    """
    private_key = str(req.get("private_key") or "").strip()
    if not private_key:
        raise HTTPException(status_code=400, detail="private_key is required")

    proj = _svc._projects.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="project not found")

    try:
        from core.harness.infrastructure.crypto.signature import sign_skill as sign_proj
        import hashlib

        # Compute project integrity from the per-project JSON
        proj_dir = Path(os.environ.get("AIPLAT_HOME", str(Path.home() / ".aiplat"))) / "projects" / project_id
        proj_dir.mkdir(parents=True, exist_ok=True)
        proj_json = proj_dir / "project.json"

        # Save project to directory first
        _svc._save_projects()

        # Compute hash of project.json
        h = hashlib.sha256()
        if proj_json.exists():
            h.update(proj_json.read_bytes())
        bundle_sha256 = h.hexdigest()

        version = req.get("version") or proj.get("version", "0.1.0")
        signature = sign_proj(private_key=private_key, skill_id=project_id, version=str(version), bundle_sha256=bundle_sha256)

        manifest_path = proj_dir / "PROJECT.manifest.json"
        manifest = {}
        if manifest_path.exists():
            try:
                manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                _log.warning("无法解析项目 manifest JSON: %s", manifest_path, exc_info=True)
        manifest["signature"] = signature
        manifest["version"] = str(version)
        manifest_path.write_text(_json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid private key: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Signing failed: {str(e)}")

    return {"status": "signed", "bundle_sha256": bundle_sha256, "version": str(version), "signature": signature}
