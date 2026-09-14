"""FDE delivery pipeline session API — start / query / approve + Phase 3 Builder link."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.fde.api.schemas import FdeItemResponse, FdeListResponse, FdeStatusResponse

router = APIRouter(tags=["fde-delivery-pipeline"])


class StartDeliveryPipelineRequest(BaseModel):
    template_id: str = "fde_delivery_v1"
    customer_name: str = ""
    domain_id: str = ""
    actor: str = "fde_engineer"
    builder_project_id: str = ""


class ApproveDeliveryPipelineRequest(BaseModel):
    feedback: str = ""


class LinkBuilderRequest(BaseModel):
    builder_project_id: str = Field(..., min_length=1)


async def _observe_builder(session_id: str, project_id: str) -> Dict[str, Any]:
    """Observe Builder via CoreFacade — never rebuild inside FDE."""
    from core.api.core_facade import (
        attach_fde_delivery_builder_observation,
        get_builder_project_service,
    )

    try:
        svc = get_builder_project_service()
        state = await svc.get_project_state(project_id)
        if not isinstance(state, dict):
            state = {"phase": "error", "detail": "invalid_builder_state"}
        if not state.get("project_id"):
            state = {**state, "project_id": project_id}
        return attach_fde_delivery_builder_observation(session_id, state)
    except Exception as e:
        return attach_fde_delivery_builder_observation(
            session_id,
            {
                "project_id": project_id,
                "phase": "error",
                "detail": str(e)[:300],
            },
        )


@router.post("/delivery-pipeline/start", response_model=FdeItemResponse)
async def start_delivery_pipeline(req: StartDeliveryPipelineRequest) -> Dict[str, Any]:
    """Start a queryable fde_delivery_v1 session (server-side stage cursor)."""
    try:
        from core.api.core_facade import (
            DomainRouter,
            start_fde_delivery_session,
        )
        domain_id = req.domain_id.strip()
        if domain_id:
            DomainRouter().require_known_domain(domain_id)
        session = start_fde_delivery_session(
            template_id=req.template_id or "fde_delivery_v1",
            customer_name=req.customer_name,
            domain_id=domain_id,
            actor=req.actor,
            builder_project_id=req.builder_project_id or "",
        )
        if session.get("builder_project_id"):
            session = await _observe_builder(session["session_id"], session["builder_project_id"])
        return session
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)[:200]) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)[:200]) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200]) from e


@router.get("/delivery-pipeline/{session_id}", response_model=FdeItemResponse)
async def get_delivery_pipeline(session_id: str) -> Dict[str, Any]:
    from core.api.core_facade import get_fde_delivery_session

    session = get_fde_delivery_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session_not_found")
    return session


@router.get("/delivery-pipeline", response_model=FdeListResponse)
async def list_delivery_pipelines(limit: int = 20) -> Dict[str, Any]:
    from core.api.core_facade import list_fde_delivery_sessions

    items = list_fde_delivery_sessions(limit=min(limit, 50))
    return {"items": items, "total": len(items)}


@router.post("/delivery-pipeline/{session_id}/approve", response_model=FdeItemResponse)
async def approve_delivery_pipeline(
    session_id: str, req: Optional[ApproveDeliveryPipelineRequest] = None
) -> Dict[str, Any]:
    """Approve current HITL pause; Phase 3 eval when Builder linked."""
    try:
        from core.api.core_facade import approve_fde_delivery_session

        return approve_fde_delivery_session(
            session_id, feedback=(req.feedback if req else "")
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="session_not_found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200]) from e


@router.post("/delivery-pipeline/{session_id}/link-builder", response_model=FdeItemResponse)
async def link_builder(session_id: str, req: LinkBuilderRequest) -> Dict[str, Any]:
    """Link existing Builder project_id; then observe factory state."""
    try:
        from core.api.core_facade import link_fde_delivery_builder_project

        link_fde_delivery_builder_project(session_id, req.builder_project_id)
        return await _observe_builder(session_id, req.builder_project_id.strip())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="session_not_found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)[:200]) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200]) from e


@router.post("/delivery-pipeline/{session_id}/observe-builder", response_model=FdeItemResponse)
async def observe_builder(session_id: str) -> Dict[str, Any]:
    """Refresh Builder observation (start/observe only — no parallel FDE build)."""
    from core.api.core_facade import get_fde_delivery_session

    session = get_fde_delivery_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session_not_found")
    pid = (session.get("builder_project_id") or "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="builder_project_id_not_linked")
    return await _observe_builder(session_id, pid)


@router.post("/delivery-pipeline/{session_id}/start-builder", response_model=FdeStatusResponse)
async def start_builder_pipeline(session_id: str) -> Dict[str, Any]:
    """Trigger Builder start_pipeline for linked project (factory path only)."""
    from core.api.core_facade import get_builder_project_service, get_fde_delivery_session

    session = get_fde_delivery_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session_not_found")
    pid = (session.get("builder_project_id") or "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="builder_project_id_not_linked")
    try:
        svc = get_builder_project_service()
        result = await svc.start_pipeline(pid)
        await _observe_builder(session_id, pid)
        return {
            "status": "ok",
            "message": "builder_start_requested",
            "data": {"builder": result, "session_id": session_id, "builder_project_id": pid},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:200]) from e


@router.post("/delivery-pipeline/{session_id}/evaluate", response_model=FdeItemResponse)
async def evaluate_delivery(session_id: str) -> Dict[str, Any]:
    from core.api.core_facade import evaluate_fde_delivery_session, get_fde_delivery_session

    try:
        evaluate_fde_delivery_session(session_id)
        session = get_fde_delivery_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="session_not_found")
        return session
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="session_not_found")
