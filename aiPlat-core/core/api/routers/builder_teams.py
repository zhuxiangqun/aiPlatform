"""
Builder team API router.

Endpoints:
  POST /builder/teams              — assemble team
  GET  /builder/teams              — list teams
  GET  /builder/teams/{id}         — get team
  POST /builder/teams/{id}/run     — run team
  POST /builder/teams/{id}/approve — approve current HITL stage
  POST /builder/teams/{id}/reject  — reject current HITL stage
  GET  /builder/teams/{id}/state   — get pipeline state
"""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api.deps import actor_from_http
from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime
from core.schemas_builder import TeamAssembleRequest, BuilderRejectRequest
from core.services.builder_team_service import BuilderTeamService

router = APIRouter(prefix="/builder")

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]

_team_svc: Optional[BuilderTeamService] = None


def _svc(rt: Optional[KernelRuntime] = None) -> BuilderTeamService:
    global _team_svc
    if _team_svc is None:
        model = None
        if rt and hasattr(rt, "adapter_manager") and rt.adapter_manager:
            try:
                model = rt.adapter_manager.get_default_adapter()
            except Exception:
                pass
        _team_svc = BuilderTeamService(model=model)
    return _team_svc


@router.post("/teams")
async def create_team(http_request: Request, rt: RuntimeDep = None):
    body = await http_request.json()
    print(f"[builder_teams] create_team body keys: {list(body.keys()) if isinstance(body, dict) else type(body)} stages_count: {len(body.get('stages', [])) if isinstance(body, dict) else 'n/a'}")
    try:
        req = TeamAssembleRequest(**body)
        return await _svc(rt).create_team(req)
    except Exception as e:
        print(f"[builder_teams] ERROR: {e}")
        import traceback; traceback.print_exc()
        raise HTTPException(500, str(e))


@router.get("/teams")
async def list_teams(rt: RuntimeDep = None):
    return {"teams": await _svc(rt).list_teams()}


@router.get("/teams/{team_id}")
async def get_team(team_id: str, rt: RuntimeDep = None):
    team = await _svc(rt).get_team(team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    return team


@router.put("/teams/{team_id}")
async def update_team(team_id: str, request: TeamAssembleRequest, rt: RuntimeDep = None):
    team = await _svc(rt).update_team(team_id, request)
    if not team:
        raise HTTPException(404, "Team not found")
    return team


@router.delete("/teams/{team_id}")
async def delete_team(team_id: str, rt: RuntimeDep = None):
    ok = await _svc(rt).delete_team(team_id)
    return {"ok": ok}


@router.post("/teams/{team_id}/run")
async def run_team(team_id: str, request: TeamAssembleRequest, rt: RuntimeDep = None):
    return await _svc(rt).run_team(team_id, request.description)


@router.post("/teams/{team_id}/approve")
async def approve_stage(team_id: str, rt: RuntimeDep = None):
    return await _svc(rt).approve_stage(team_id)


@router.post("/teams/{team_id}/reject")
async def reject_stage(team_id: str, request: BuilderRejectRequest, rt: RuntimeDep = None):
    return await _svc(rt).reject_stage(team_id, request.feedback)


@router.get("/teams/{team_id}/state")
async def get_team_state(team_id: str, rt: RuntimeDep = None):
    return await _svc(rt).get_team_state(team_id)
