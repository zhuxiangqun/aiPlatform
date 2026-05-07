"""
Builder pipeline API router.

Endpoints:
  POST /builder/sessions              — create session
  POST /builder/sessions/{id}/chat     — PM dialogue
  POST /builder/sessions/{id}/confirm  — confirm PRD
  POST /builder/sessions/{id}/start    — start pipeline

  POST /builder/sessions/{id}/approve-architecture  — HITL: approve architecture
  POST /builder/sessions/{id}/reject-architecture   — HITL: reject architecture
  POST /builder/sessions/{id}/approve-test-plan     — HITL: approve test cases
  POST /builder/sessions/{id}/reject-test-plan      — HITL: reject test cases

  GET  /builder/sessions/{id}          — get state
"""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api.deps import actor_from_http
from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime
from core.schemas_builder import (
    BuilderSessionCreateRequest,
    BuilderChatRequest,
    BuilderChatResponse,
    BuilderRejectRequest,
    BuilderSessionStateResponse,
)
from core.services.builder_session import BuilderSessionService

router = APIRouter(prefix="/builder")

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]

_builder_svc: Optional[BuilderSessionService] = None


def _svc(rt: Optional[KernelRuntime] = None) -> BuilderSessionService:
    global _builder_svc
    if _builder_svc is None:
        model = None
        if rt and hasattr(rt, "adapter_manager") and rt.adapter_manager:
            try:
                model = rt.adapter_manager.get_default_adapter()
            except Exception:
                pass
        _builder_svc = BuilderSessionService(model=model)
    return _builder_svc


@router.post("/sessions")
async def create_session(request: BuilderSessionCreateRequest, http_request: Request, rt: RuntimeDep = None):
    actor = actor_from_http(http_request, request.model_dump())
    session_id = await _svc(rt).create_session(
        requirement=request.requirement,
        tenant_id=request.tenant_id or actor.get("tenant_id", "default"),
        user_id=request.user_id or actor.get("actor_id", "system"),
    )
    return {"session_id": session_id}


@router.post("/sessions/{session_id}/chat")
async def chat(session_id: str, request: BuilderChatRequest, rt: RuntimeDep = None) -> BuilderChatResponse:
    return await _svc(rt).chat(session_id, request.message)


@router.post("/sessions/{session_id}/confirm")
async def confirm(session_id: str, rt: RuntimeDep = None) -> BuilderSessionStateResponse:
    return await _svc(rt).confirm_requirements(session_id)


@router.post("/sessions/{session_id}/start")
async def start_pipeline(session_id: str, rt: RuntimeDep = None) -> BuilderSessionStateResponse:
    return await _svc(rt).start_pipeline(session_id)


@router.post("/sessions/{session_id}/approve-architecture")
async def approve_architecture(session_id: str, rt: RuntimeDep = None) -> BuilderSessionStateResponse:
    return await _svc(rt).approve_architecture(session_id)


@router.post("/sessions/{session_id}/reject-architecture")
async def reject_architecture(session_id: str, request: BuilderRejectRequest, rt: RuntimeDep = None) -> BuilderSessionStateResponse:
    return await _svc(rt).reject_architecture(session_id, request.feedback)


@router.post("/sessions/{session_id}/approve-test-plan")
async def approve_test_plan(session_id: str, rt: RuntimeDep = None) -> BuilderSessionStateResponse:
    return await _svc(rt).approve_test_plan(session_id)


@router.post("/sessions/{session_id}/reject-test-plan")
async def reject_test_plan(session_id: str, request: BuilderRejectRequest, rt: RuntimeDep = None) -> BuilderSessionStateResponse:
    return await _svc(rt).reject_test_plan(session_id, request.feedback)


@router.get("/sessions/{session_id}")
async def get_state(session_id: str, rt: RuntimeDep = None) -> BuilderSessionStateResponse:
    return await _svc(rt).get_state(session_id)
