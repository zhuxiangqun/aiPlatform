"""
Builder API router — backed by platform-local builder services.
Each endpoint proxies to the local Builder service with proper type deserialization.
"""

from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException

from builder.builder_project_service import BuilderProjectService
from builder.builder_session import BuilderSessionService
from builder.builder_team_service import BuilderTeamService
from core.schemas_builder import (
    BuilderChatRequest,
    BuilderSessionCreateRequest,
    ProjectCreateRequest,
    TeamAssembleRequest,
)

router = APIRouter(prefix="/platform/builder", tags=["builder"])

_team_svc = BuilderTeamService()
_svc = BuilderProjectService(team_service=_team_svc)
_session_svc = BuilderSessionService()


# ---- Sessions ----

@router.post("/sessions")
async def create_builder_session(req: BuilderSessionCreateRequest):
    return await _session_svc.create_session(req.requirement)

@router.post("/sessions/{session_id}/chat")
async def builder_chat(session_id: str, req: BuilderChatRequest):
    return await _session_svc.chat(session_id, req.message)

@router.post("/sessions/{session_id}/confirm")
async def session_confirm(session_id: str):
    return await _session_svc.confirm_requirement(session_id)

@router.post("/sessions/{session_id}/start")
async def session_start(session_id: str):
    return await _session_svc.start_pipeline(session_id)

@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    return await _session_svc.get_session(session_id)

# ---- Session HITL (architecture / test plan approval) ----

@router.post("/sessions/{session_id}/approve-architecture")
async def session_approve_architecture(session_id: str):
    return await _session_svc.approve_architecture(session_id)

@router.post("/sessions/{session_id}/reject-architecture")
async def session_reject_architecture(session_id: str, feedback: str = ""):
    return await _session_svc.reject_architecture(session_id, feedback)

@router.post("/sessions/{session_id}/approve-test-plan")
async def session_approve_test_plan(session_id: str):
    return await _session_svc.approve_test_plan(session_id)

@router.post("/sessions/{session_id}/reject-test-plan")
async def session_reject_test_plan(session_id: str, feedback: str = ""):
    return await _session_svc.reject_test_plan(session_id, feedback)


# ---- Projects ----

@router.get("/projects")
async def list_projects():
    projects = await _svc.list_projects()
    result = [p.model_dump() if hasattr(p, 'model_dump') else p for p in projects]
    return {"projects": result, "total": len(result)}

@router.post("/projects")
async def create_project(req: ProjectCreateRequest):
    return await _svc.create_project(req)

@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    return await _svc.get_project(project_id)

@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    return await _svc.delete_project(project_id)

@router.get("/projects/{project_id}/state")
async def get_project_state(project_id: str):
    return await _svc.get_project_state(project_id)

@router.post("/projects/{project_id}/chat")
async def project_chat(project_id: str, req: BuilderChatRequest):
    return await _svc.chat(project_id, req.message)

@router.post("/projects/{project_id}/confirm")
async def project_confirm(project_id: str):
    return await _svc.confirm_prd(project_id)

@router.post("/projects/{project_id}/recommend-team")
async def recommend_team(project_id: str):
    """AI analyzes PRD and recommends a team configuration."""
    return await _svc.recommend_team(project_id)

@router.post("/projects/{project_id}/start")
async def project_start(project_id: str):
    return await _svc.start_pipeline(project_id)

@router.post("/projects/{project_id}/approve")
async def project_approve(project_id: str):
    return await _svc.approve_stage(project_id)

@router.post("/projects/{project_id}/reject")
async def project_reject(project_id: str, feedback: str = ""):
    return await _svc.reject_stage(project_id, feedback)

@router.post("/projects/{project_id}/rollback/{stage_id:path}")
async def project_rollback(project_id: str, stage_id: str):
    return await _svc.rollback_stage(project_id, stage_id)

@router.post("/projects/{project_id}/fix")
async def project_fix(project_id: str):
    return await _svc.fix_stage(project_id)

@router.post("/projects/{project_id}/resume/{stage_id:path}")
async def project_resume(project_id: str, stage_id: str):
    """Resume pipeline from a specific stage (rollback without clearing artifacts)."""
    return await _svc.resume_from_stage(project_id, stage_id)

@router.get("/projects/{project_id}/deploy")
async def project_deploy(project_id: str):
    deploy_dir = await _svc.get_deploy_dir(project_id)
    if not deploy_dir:
        raise HTTPException(404, detail="Deploy package not ready. Run pipeline first.")
    return {"project_id": project_id, "deploy_dir": deploy_dir}


# ---- Teams ----

@router.post("/teams")
async def create_team(req: TeamAssembleRequest):
    return await _team_svc.create_team(req)

@router.get("/teams")
async def list_teams():
    teams = await _team_svc.list_teams()
    return {"teams": [t.model_dump() if hasattr(t, 'model_dump') else t for t in teams], "total": len(teams)}

@router.get("/teams/{team_id}")
async def get_team(team_id: str):
    return await _team_svc.get_team(team_id)

@router.put("/teams/{team_id}")
async def update_team(team_id: str, req: TeamAssembleRequest):
    result = await _team_svc.update_team(team_id, req)
    if not result:
        raise HTTPException(404, detail="Team not found")
    return result

@router.delete("/teams/{team_id}")
async def delete_team(team_id: str):
    return await _team_svc.delete_team(team_id)

@router.post("/teams/{team_id}/run")
async def run_team(team_id: str, body: Dict[str, Any]):
    return await _team_svc.run_team(team_id, body.get("description", ""))


@router.get("/projects/{project_id}/graph")
async def get_pipeline_graph(project_id: str):
    """Return pipeline execution graph data for visualization."""
    return await _svc.get_graph(project_id)


@router.post("/projects/{project_id}/test")
async def run_project_tests(project_id: str):
    """Run E2E smoke + repo tests for a completed project pipeline."""
    return await _svc.run_tests(project_id)


@router.post("/projects/{project_id}/deploy-to-app")
async def deploy_project_to_app(project_id: str):
    """Deploy pipeline output to the app layer."""
    return await _svc.deploy_to_app(project_id)


# ---- Agent Insights ----

@router.get("/agent-insight/{agent_id}")
async def get_agent_insight(agent_id: str):
    """Get insight metrics for a single agent."""
    return await _svc.get_agent_insight(agent_id)


@router.get("/agent-insights")
async def list_agent_insights():
    """Get insight metrics for all agents."""
    return await _svc.list_agent_insights()


@router.post("/agent-insights/refresh")
async def refresh_agent_insights():
    """Refresh agent insight metrics."""
    return await _svc.refresh_agent_insights()
