"""GrillingBridge API — cross-cutting requirements clarification endpoints."""

from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
import logging

router = APIRouter(prefix="/grilling", tags=["grilling"])


class StartGrillRequest(BaseModel):
    entry_point: str
    domain_id: str = ""
    context: Optional[Dict[str, Any]] = None


class AnswerRequest(BaseModel):
    session_id: str
    answer: str


@router.post("/start", response_model=Dict[str, Any])
async def start_grill(req: StartGrillRequest):
    """Start a grilling clarification interview. Returns first question."""
    from core.api.core_facade import start_grilling
    result = start_grilling(req.entry_point, req.domain_id, req.context)
    return result


@router.post("/answer", response_model=Dict[str, Any])
async def answer_grill(req: AnswerRequest):
    """Submit answer to current question. Returns next question or finalize."""
    from core.api.core_facade import continue_grilling
    if not req.answer or not req.answer.strip():
        raise HTTPException(status_code=400, detail="Answer cannot be empty")
    result = continue_grilling(req.session_id, req.answer.strip())
    return result


@router.post("/skip", response_model=Dict[str, Any])
async def skip_grill(req: AnswerRequest):
    """Skip current non-required question."""
    from core.api.core_facade import skip_grilling_question
    result = skip_grilling_question(req.session_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "Cannot skip"))
    return result


@router.get("/progress/{session_id}", response_model=Dict[str, Any])
async def progress_grill(session_id: str):
    """Get current grilling session state for UI recovery on page refresh."""
    from core.api.core_facade import get_grilling_progress
    return get_grilling_progress(session_id)


class FinalizeRequest(BaseModel):
    session_id: str


@router.post("/finalize", response_model=Dict[str, Any])
async def finalize_grill(req: FinalizeRequest):
    """Skip remaining questions and finalize the grilling session."""
    from core.api.core_facade import _finalize_grilling
    return _finalize_grilling(req.session_id)
