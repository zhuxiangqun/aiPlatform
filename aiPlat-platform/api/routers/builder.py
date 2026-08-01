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
from api.schemas_response import ProjectListResponse, ProjectStateResponse, PipelineStartResponse, TeamListResponse, StatusResponse

_svc = None


def _get_svc():
    global _svc
    if _svc is None:
        from builder.builder_project_service import _get_project_service
        _svc = _get_project_service()
    return _svc

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


def _team_get_svc():
    return _team_svc

_deprecation_header = {"Deprecation": "true", "Sunset": "Sat, 01 Jan 2027 00:00:00 GMT",
                        "Link": '</api/v2/projects>; rel="successor-version"'}


def _legacy_response(data: dict) -> JSONResponse:
    """Wrap legacy /sessions/ response with deprecation headers."""
    return JSONResponse(content=data, headers=_deprecation_header)


# ---- Sessions (legacy, forward to projects) ----

@router.post("/sessions", response_model=StatusResponse)
async def create_builder_session(req: BuilderSessionCreateRequest, _auth: str = Depends(require_builder_access)):
    """Legacy: auto-create project from requirement and return session info."""
    proj = await _get_svc().create_project(ProjectCreateRequest(name=req.requirement[:30] or "新项目", description=req.requirement))
    return _legacy_response({"session_id": proj.project_id, "phase": "dialogue"})

@router.post("/sessions/{session_id}/chat", response_model=StatusResponse)
async def builder_chat(session_id: str, req: BuilderChatRequest, _auth: str = Depends(require_builder_access)):
    return _legacy_response(await _get_svc().chat(session_id, req.message))

@router.post("/sessions/{session_id}/confirm", response_model=StatusResponse)
async def session_confirm(session_id: str, _auth: str = Depends(require_builder_access)):
    return _legacy_response(await _get_svc().confirm_prd(session_id))

@router.post("/sessions/{session_id}/start", response_model=StatusResponse)
async def session_start(session_id: str, _auth: str = Depends(require_builder_access)):
    return _legacy_response(await _get_svc().start_pipeline(session_id))

@router.get("/sessions/{session_id}", response_model=StatusResponse)
async def get_session(session_id: str, _auth: str = Depends(require_builder_access)):
    return _legacy_response(await _get_svc().get_project_state(session_id))

# ---- Session HITL (legacy, forward to projects) ----

@router.post("/sessions/{session_id}/approve-architecture", response_model=StatusResponse)
async def session_approve_architecture(session_id: str, _auth: str = Depends(require_builder_access)):
    return _legacy_response(await _get_svc().approve_stage(session_id))

@router.post("/sessions/{session_id}/reject-architecture", response_model=StatusResponse)
async def session_reject_architecture(session_id: str, feedback: str = "", _auth: str = Depends(require_builder_access)):
    return _legacy_response(await _get_svc().reject_stage(session_id, feedback))

@router.post("/sessions/{session_id}/approve-test-plan", response_model=StatusResponse)
async def session_approve_test_plan(session_id: str, _auth: str = Depends(require_builder_access)):
    return _legacy_response(await _get_svc().approve_stage(session_id))

@router.post("/sessions/{session_id}/reject-test-plan", response_model=StatusResponse)
async def session_reject_test_plan(session_id: str, feedback: str = "", _auth: str = Depends(require_builder_access)):
    return _legacy_response(await _get_svc().reject_stage(session_id, feedback))


# ---- Projects ----

@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(_auth: str = Depends(require_builder_access)):
    projects = await _get_svc().list_projects()
    result = [p.model_dump() if hasattr(p, 'model_dump') else p for p in projects]
    return {"projects": result, "total": len(result)}

@router.post("/projects", response_model=StatusResponse)
async def create_project(req: ProjectCreateRequest, _auth: str = Depends(require_admin_access)):
    project = await _get_svc().create_project(req)
    return project.model_dump() if hasattr(project, 'model_dump') else project

@router.get("/projects/{project_id}", response_model=StatusResponse)
async def get_project(project_id: str, _auth: str = Depends(require_builder_access)):
    return await _get_svc().get_project(project_id)

@router.delete("/projects/{project_id}", response_model=StatusResponse)
async def delete_project(project_id: str, _auth: str = Depends(require_builder_access)):
    ok = await _get_svc().delete_project(project_id)
    return {"status": "ok" if ok else "error", "detail": "" if ok else "项目不存在"}

@router.post("/projects/batch-delete", response_model=StatusResponse)
async def batch_delete_projects(req: Dict[str, Any], _auth: str = Depends(require_builder_access)):
    """Batch delete projects. Body: { "project_ids": ["prj_xxx", ...], "pass_rate_below": 0.01 }"""
    project_ids = req.get("project_ids")
    pass_rate_below = req.get("pass_rate_below")
    deleted = await _get_svc().batch_delete(
        project_ids=project_ids,
        pass_rate_below=pass_rate_below,
    )
    return {"deleted": deleted}

@router.get("/projects/{project_id}/state", response_model=ProjectStateResponse)
async def get_project_state(project_id: str, _auth: str = Depends(require_builder_access)):
    return await _get_svc().get_project_state(project_id)

@router.get("/projects/{project_id}/messages", response_model=StatusResponse)
async def get_project_messages(project_id: str, _auth: str = Depends(require_builder_access)):
    return await _get_svc().get_messages(project_id)

@router.post("/projects/{project_id}/chat", response_model=StatusResponse)
async def project_chat(project_id: str, req: BuilderChatRequest, _auth: str = Depends(require_builder_access)):
    return await _get_svc().chat(project_id, req.message)

@router.post("/projects/{project_id}/confirm", response_model=StatusResponse)
async def project_confirm(project_id: str, body: Dict[str, Any] = {}, _auth: str = Depends(require_builder_access)):
    return await _get_svc().confirm_prd(project_id, prd_data=body.get("prd"))

@router.post("/projects/{project_id}/recommend-team", response_model=StatusResponse)
async def recommend_team(project_id: str, _auth: str = Depends(require_builder_access)):
    """AI analyzes PRD and recommends a team configuration."""
    return await _get_svc().recommend_team(project_id)

@router.post("/projects/{project_id}/start", response_model=PipelineStartResponse)
async def project_start(project_id: str, _auth: str = Depends(require_builder_access)):
    return await _get_svc().start_pipeline(project_id)

@router.post("/projects/{project_id}/approve", response_model=StatusResponse)
async def project_approve(project_id: str, body: Dict[str, Any] = {}, _auth: str = Depends(require_builder_access)):
    feedback = str(body.get("feedback", "") or "")
    return await _get_svc().approve_stage(project_id, feedback=feedback)

@router.post("/projects/{project_id}/reject", response_model=StatusResponse)
async def project_reject(project_id: str, body: Dict[str, Any] = {}, _auth: str = Depends(require_builder_access)):
    feedback = str(body.get("feedback", "") or "")
    return await _get_svc().reject_stage(project_id, feedback)

@router.post("/projects/{project_id}/rollback/{stage_id:path}", response_model=StatusResponse)
async def project_rollback(project_id: str, stage_id: str, _auth: str = Depends(require_builder_access)):
    return await _get_svc().rollback_stage(project_id, stage_id)


@router.post("/projects/{project_id}/rollback-prd", response_model=StatusResponse)
async def project_rollback_prd(project_id: str, _auth: str = Depends(require_builder_access)):
    """Roll back to PRD editing phase — clears pipeline state and confirmed PRD."""
    return await _get_svc().rollback_prd(project_id)

@router.post("/projects/{project_id}/fix", response_model=StatusResponse)
async def project_fix(project_id: str, _auth: str = Depends(require_builder_access)):
    return await _get_svc().start_fix(project_id)

@router.post("/projects/{project_id}/resume/{stage_id:path}", response_model=StatusResponse)
async def project_resume(project_id: str, stage_id: str, _auth: str = Depends(require_builder_access)):
    """Resume pipeline from a specific stage (rollback without clearing artifacts)."""
    return await _get_svc().resume_from_stage(project_id, stage_id)

@router.get("/projects/{project_id}/deploy", response_model=StatusResponse)
async def project_deploy(project_id: str, _auth: str = Depends(require_builder_access)):
    deploy_dir = await _get_svc().get_deploy_dir(project_id)
    if not deploy_dir:
        raise HTTPException(404, detail="Deploy package not ready. Run pipeline first.")
    return {"project_id": project_id, "deploy_dir": deploy_dir}


# ---- Teams ----

@router.post("/teams", response_model=StatusResponse)
async def create_team(req: TeamAssembleRequest, _auth: str = Depends(require_builder_access)):
    return await _team_get_svc().create_team(req)

@router.get("/teams", response_model=TeamListResponse)
async def list_teams(_auth: str = Depends(require_builder_access)):
    teams = await _team_get_svc().list_teams()
    return {"teams": [t.model_dump() if hasattr(t, 'model_dump') else t for t in teams], "total": len(teams)}

@router.get("/teams/{team_id}", response_model=StatusResponse)
async def get_team(team_id: str, _auth: str = Depends(require_builder_access)):
    return await _team_get_svc().get_team(team_id)

@router.put("/teams/{team_id}", response_model=StatusResponse)
async def update_team(team_id: str, req: TeamAssembleRequest, _auth: str = Depends(require_builder_access)):
    result = await _team_get_svc().update_team(team_id, req)
    if not result:
        raise HTTPException(404, detail="Team not found")
    return result

@router.delete("/teams/{team_id}", response_model=StatusResponse)
async def delete_team(team_id: str, _auth: str = Depends(require_admin_access)):
    return await _team_get_svc().delete_team(team_id)

@router.post("/teams/{team_id}/run", response_model=StatusResponse)
async def run_team(team_id: str, body: Dict[str, Any], _auth: str = Depends(require_builder_access)):
    return await _team_get_svc().run_team(team_id, body.get("description", ""))


@router.get("/projects/{project_id}/graph", response_model=StatusResponse)
async def get_pipeline_graph(project_id: str, _auth: str = Depends(require_builder_access)):
    """Return pipeline execution graph data for visualization."""
    return await _get_svc().get_graph(project_id)


@router.post("/projects/{project_id}/test", response_model=StatusResponse)
async def run_project_tests(project_id: str, _auth: str = Depends(require_builder_access)):
    """Run E2E smoke + repo tests for a completed project pipeline."""
    return await _get_svc().run_tests(project_id)


@router.post("/projects/{project_id}/regenerate", response_model=StatusResponse)
async def regenerate_project_stage(project_id: str, req: Dict[str, Any], _auth: str = Depends(require_builder_access)):
    """Regenerate a specific stage with human feedback, then resume pipeline."""
    stage_id = str(req.get("stage_id") or "")
    feedback = str(req.get("feedback") or "")
    if not stage_id or not feedback:
        raise HTTPException(400, detail="stage_id and feedback are required")
    return await _get_svc().regenerate_stage(project_id, stage_id, feedback)


@router.post("/projects/{project_id}/deploy-to-app", response_model=StatusResponse)
async def deploy_project_to_app(project_id: str, _auth: str = Depends(require_builder_access)):
    """Deploy pipeline output to aiPlat-app (port 8004)."""
    # Verify project signature before deploy
    try:
        proj = _get_svc()._projects.get(project_id)
        if proj and proj.get("metadata", {}).get("provenance", {}).get("signature"):
            import os, json as _json, hashlib as _hashlib
            from core.api.core_facade import verify_skill_signature  # v2.5: canonical path
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
    return await _get_svc().deploy_to_app(project_id)


@router.get("/agent-insight/{agent_id}", response_model=StatusResponse)
async def get_agent_insight(agent_id: str, _auth: str = Depends(require_builder_access)):
    """Get insight metrics for a single agent."""
    return await _get_svc().get_agent_insight(agent_id)


@router.get("/agent-insights", response_model=StatusResponse)
async def list_agent_insights(_auth: str = Depends(require_builder_access)):
    """Get insight metrics for all agents."""
    return await _get_svc().list_agent_insights()


@router.post("/agent-insights/refresh", response_model=StatusResponse)
async def refresh_agent_insights(_auth: str = Depends(require_builder_access)):
    """Refresh agent insight metrics."""
    return await _get_svc().refresh_agent_insights()


@router.get("/projects/{project_id}/health-report", response_model=StatusResponse)
async def get_project_health_report(project_id: str, _auth: str = Depends(require_builder_access)):
    """Get pipeline health report with per-stage dimensional scores."""
    return await _get_svc().get_health_report(project_id)


@router.get("/projects/{project_id}/export", response_model=StatusResponse)
async def export_project_state(project_id: str, _auth: str = Depends(require_builder_access)):
    """Export full project execution state as downloadable JSON."""
    state = await _get_svc().get_project_state(project_id)
    return JSONResponse(
        content=state,
        headers={"Content-Disposition": f'attachment; filename="aiplat_{project_id}_export.json"'}
    )


@router.post("/projects/{project_id}/sign", response_model=StatusResponse)
async def sign_project(project_id: str, req: Dict[str, Any], _auth: str = Depends(require_admin_access)):
    """
    Sign a project directory with an Ed25519 private key.
    Writes PROJECT.manifest.json into the project directory.
    """
    private_key = str(req.get("private_key") or "").strip()
    if not private_key:
        raise HTTPException(status_code=400, detail="private_key is required")

    proj = _get_svc()._projects.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="project not found")

    try:
        from core.api.core_facade import sign_skill as sign_proj  # v2.5: canonical path
        import hashlib

        # Compute project integrity from the per-project JSON
        proj_dir = Path(os.environ.get("AIPLAT_HOME", str(Path.home() / ".aiplat"))) / "projects" / project_id
        proj_dir.mkdir(parents=True, exist_ok=True)
        proj_json = proj_dir / "project.json"

        # Save project to directory first
        _get_svc()._save_projects()

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
