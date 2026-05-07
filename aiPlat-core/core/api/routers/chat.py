"""
Universal Chat API router.

Endpoints:
  POST /chat/sessions        — create chat session (agent_id + system_prompt)
  POST /chat/sessions/{id}/chat  — send message
  GET  /chat/sessions/{id}   — get session state
"""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime
from core.services.chat_service import ChatService

router = APIRouter(prefix="/chat")

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]

_chat_svc: Optional[ChatService] = None


def _svc(rt: Optional[KernelRuntime] = None) -> ChatService:
    global _chat_svc
    if _chat_svc is None or (_chat_svc._model is None):
        model = None
        if rt and hasattr(rt, "adapter_manager") and rt.adapter_manager:
            try:
                model = rt.adapter_manager.get_default_adapter()
            except Exception:
                pass
        if model is None:
            try:
                import os
                from core.harness.utils.model_injection import create_selected_adapter
                model_name = os.getenv("AIPLAT_LLM_MODEL") or "deepseek-chat"
                model = create_selected_adapter(model_name=model_name)
            except Exception as e:
                print(f"[chat] create_selected_adapter failed: {e}")
        _chat_svc = ChatService(model=model)
    return _chat_svc


@router.post("/sessions")
async def create_session(request: dict, rt: RuntimeDep = None):
    agent_id = request.get("agent_id", "")
    system_prompt = request.get("system_prompt", "")
    initial_context = request.get("initial_context", {})
    session_id = await _svc(rt).create_session(agent_id, system_prompt, initial_context)
    return {"session_id": session_id}


@router.post("/sessions/{session_id}/chat")
async def chat(session_id: str, request: dict, rt: RuntimeDep = None):
    message = request.get("message", "")
    return await _svc(rt).chat(session_id, message)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, rt: RuntimeDep = None):
    s = await _svc(rt).get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    return s
