"""
Platform Chat routes — web chat session management.

Migrated from aiPlat-core/core/api/routers/chat.py per architecture contract.
"""
from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from auth.deps import require_auth
from core.api.core_facade import KernelRuntime, get_kernel_runtime
from core.api.core_facade import create_chat_service

router = APIRouter(prefix="/platform/chat", tags=["chat"])

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]

_chat_svc = None


def _svc(rt: Optional[KernelRuntime] = None):
    global _chat_svc
    if _chat_svc is None or (_chat_svc._model is None):
        from core.api.core_facade import get_chat_service_model, create_chat_service
        model = get_chat_service_model(rt)
        _chat_svc = create_chat_service(model=model)
    return _chat_svc


@router.post("/sessions")
async def create_session(request: dict, rt: RuntimeDep = None, _auth: str = Depends(require_auth)):
    agent_id = request.get("agent_id", "")
    system_prompt = request.get("system_prompt", "")
    initial_context = request.get("initial_context", {})
    session_id = await _svc(rt).create_session(agent_id, system_prompt, initial_context)
    return {"session_id": session_id}


@router.post("/sessions/{session_id}/chat")
async def chat(session_id: str, request: dict, rt: RuntimeDep = None, _auth: str = Depends(require_auth)):
    message = request.get("message", "")
    return await _svc(rt).chat(session_id, message)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, rt: RuntimeDep = None, _auth: str = Depends(require_auth)):
    s = await _svc(rt).get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    return s
