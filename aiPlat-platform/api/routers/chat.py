"""
Platform Chat routes — web chat session management.

Migrated from aiPlat-core/core/api/routers/chat.py per architecture contract.
"""
from __future__ import annotations
import logging

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from auth.deps import require_auth
from core.api.facades.runtime_facade import KernelRuntime, get_kernel_runtime
from core.api.facades.service_facade import create_chat_service
from api.schemas_response import ChatSessionResponse, ChatReplyResponse, ChatSessionDetailResponse

router = APIRouter(prefix="/platform/chat", tags=["chat"])

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]

_chat_svc = None


def _svc(rt: Optional[KernelRuntime] = None):
    global _chat_svc
    if _chat_svc is None or (_chat_svc._model is None):
        from core.api.core_facade import get_chat_service_model
        model = get_chat_service_model(rt)
        _chat_svc = create_chat_service(model=model)
    return _chat_svc


@router.post("/sessions", response_model=ChatSessionResponse)
async def create_session(request: dict, rt: RuntimeDep = None, _auth: str = Depends(require_auth)):
    agent_id = request.get("agent_id", "")
    system_prompt = request.get("system_prompt", "")
    template_id = request.get("template_id", "")
    variables = request.get("variables", {})

    # If template_id is provided, load template and use it as system_prompt
    if template_id and not system_prompt:
        try:
            store = getattr(rt, "execution_store", None) if rt else None
            if store:
                tpl = await store.get_prompt_app_template(template_id=template_id)
                if tpl:
                    sp = tpl.get("system_prompt", "")
                    up = tpl.get("user_prompt", "")
                    for k, v in variables.items():
                        up = up.replace("$" + "{" + k + "}", str(v))
                    system_prompt = (sp + "\n\n" + up).strip()
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    initial_context = request.get("initial_context", {})
    session_id = await _svc(rt).create_session(agent_id, system_prompt, initial_context)
    return {"session_id": session_id}


@router.post("/sessions/{session_id}/chat", response_model=ChatReplyResponse)
async def chat(session_id: str, request: dict, rt: RuntimeDep = None, _auth: str = Depends(require_auth)):
    message = request.get("message", "")
    return await _svc(rt).chat(session_id, message)


@router.get("/sessions/{session_id}", response_model=ChatSessionDetailResponse)
async def get_session(session_id: str, rt: RuntimeDep = None, _auth: str = Depends(require_auth)):
    s = await _svc(rt).get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    return s
