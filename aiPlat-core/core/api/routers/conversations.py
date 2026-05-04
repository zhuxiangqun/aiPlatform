from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api.deps import actor_from_http
from core.api.utils.run_contract import wrap_execution_result_as_run_summary
from core.harness.integration import KernelRuntime, get_harness
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.kernel.types import ExecutionRequest
from core.schemas_conversations import (
    ConversationCreateRequest,
    ConversationQueryRequest,
    ConversationScopeUpdateRequest,
)
from core.services.conversations import ConversationService, normalize_scope

router = APIRouter()

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]


def _svc(rt: Optional[KernelRuntime]) -> ConversationService:
    store = getattr(rt, "execution_store", None) if rt else None
    if not store:
        raise HTTPException(status_code=503, detail="Execution store not available")
    return ConversationService(store)


@router.post("/conversations")
async def create_conversation(request: ConversationCreateRequest, http_request: Request, rt: RuntimeDep = None):
    actor = actor_from_http(http_request, request.model_dump())
    tenant_id = str(request.tenant_id or actor.get("tenant_id") or "default")
    user_id = str(request.user_id or actor.get("actor_id") or "system")
    out = await _svc(rt).create_conversation_session(
        tenant_id=tenant_id,
        user_id=user_id,
        title=request.title or "资料对话",
        scope=(request.scope.model_dump(exclude_none=True) if request.scope else {"collection_id": "default", "doc_ids": []}),
        profile=request.profile.model_dump(exclude_none=True) if request.profile else {"citation_required": True, "answer_style": "concise", "language": "zh-CN"},
    )
    return out


@router.get("/conversations")
async def list_conversations(http_request: Request, user_id: Optional[str] = None, limit: int = 100, offset: int = 0, rt: RuntimeDep = None):
    actor = actor_from_http(http_request, {})
    tenant_id = str(actor.get("tenant_id") or "default")
    uid = str(user_id or actor.get("actor_id") or "system")
    return await _svc(rt).list_conversation_sessions(tenant_id=tenant_id, user_id=uid, limit=limit, offset=offset)


@router.get("/conversations/{session_id}")
async def get_conversation(session_id: str, rt: RuntimeDep = None):
    try:
        return await _svc(rt).get_conversation_session(session_id=session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="conversation_not_found")


@router.put("/conversations/{session_id}/scope")
async def update_conversation_scope(session_id: str, request: ConversationScopeUpdateRequest, http_request: Request, rt: RuntimeDep = None):
    actor = actor_from_http(http_request, request.model_dump())
    tenant_id = str(actor.get("tenant_id") or "default")
    user_id = str(actor.get("actor_id") or "system")
    current = await _svc(rt).get_conversation_session(session_id=session_id)
    scope = normalize_scope(request.model_dump(exclude_none=True), fallback=current.get("scope") or {})
    out = await _svc(rt).set_conversation_scope(
        session_id=session_id,
        tenant_id=tenant_id,
        user_id=user_id,
        title=current.get("title"),
        scope=scope,
        profile=current.get("profile") or {},
    )
    return {"ok": True, "scope": out}


@router.post("/conversations/{session_id}/query")
async def query_conversation(session_id: str, request: ConversationQueryRequest, http_request: Request, rt: RuntimeDep = None):
    actor = actor_from_http(http_request, request.model_dump())
    tenant_id = str(actor.get("tenant_id") or "default")
    user_id = str(request.user_id or actor.get("actor_id") or "system")
    svc = _svc(rt)
    convo = await svc.get_conversation_session(session_id=session_id)
    scope_applied = normalize_scope(
        request.scope_override.model_dump(exclude_none=True) if request.scope_override else convo.get("scope") or {},
        fallback=convo.get("scope") or {},
    )
    await svc.append_conversation_user_message(
        tenant_id=tenant_id,
        session_id=session_id,
        user_id=user_id,
        content=str(request.message or "").strip(),
    )
    payload: dict[str, Any] = {
        "session_id": session_id,
        "user_id": user_id,
        "message": str(request.message or "").strip(),
        "scope": scope_applied,
        "messages": [
            {"role": "user", "content": str(request.message or "").strip()},
        ],
        "options": request.options.model_dump() if request.options else {"citation_required": True, "max_citations": 8, "top_k": 8, "language": "zh-CN"},
        "context": {
            "tenant_id": tenant_id,
            "actor_id": user_id,
            "session_id": session_id,
            "scope": scope_applied,
            "profile": convo.get("profile") or {},
            "options": request.options.model_dump() if request.options else {"citation_required": True, "max_citations": 8, "top_k": 8, "language": "zh-CN"},
        },
    }
    exec_req = ExecutionRequest(kind="agent", target_id="materials_chat_agent", payload=payload, user_id=user_id, session_id=session_id)
    result = await get_harness().execute(exec_req)
    resp = wrap_execution_result_as_run_summary(result)
    resp["session_id"] = session_id
    resp["scope_applied"] = scope_applied
    return resp
