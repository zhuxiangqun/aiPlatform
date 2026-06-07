"""
Platform Conversations routes — conversation session CRUD.

Migrated from aiPlat-core/core/api/routers/conversations.py per architecture contract.
"""
from __future__ import annotations


from typing import Annotated, Any, Optional, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api.deps import actor_from_http
from core.api.utils.run_contract import wrap_execution_result_as_run_summary
from core.api.facades.runtime_facade import KernelRuntime, ExecutionRequest, get_kernel_runtime
from core.api.facades.service_facade import create_conversation_service
from core.api.facades.service_facade import normalize_conversation_scope
from core.schemas_conversations import (
    ConversationCreateRequest,
    ConversationQueryRequest,
    ConversationScopeUpdateRequest,
)

router = APIRouter(prefix="/platform", tags=["conversations"])

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]


def _ensure_runtime() -> None:
    """Lazily initialize KernelRuntime in the platform process when needed."""
    rt = get_kernel_runtime()
    if rt is None:
        _init_platform_runtime()


def _init_platform_runtime() -> None:
    """Bootstrap a minimal KernelRuntime in the platform process."""
    import os
    from core.management.agent_manager import AgentManager
    from core.management.skill_manager import SkillManager
    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.api.core_facade import AgentDiscovery, AgentLoader, AgentRegistry, get_agent_registry_facade as get_agent_registry

    db_path = os.path.expanduser(os.getenv("AIPLAT_EXECUTION_DB_PATH", "~/.aiplat/data/execution.db"))
    store = ExecutionStore(ExecutionStoreConfig(db_path=db_path))
    agent_mgr = AgentManager(seed=False, scope="engine")
    ws_agent_mgr = AgentManager(seed=False, scope="workspace", reserved_ids=set(agent_mgr.get_agent_ids()))
    skill_mgr = SkillManager(seed=False, scope="engine")

    # Seed AgentRegistry with discovered agents (needed by HarnessIntegration._execute_agent)
    agent_reg = get_agent_registry()
    discovery = AgentDiscovery(agent_manager=agent_mgr, workspace_agent_manager=ws_agent_mgr)
    loader = AgentLoader(registry=agent_reg)
    discovered = discovery.discover_all()
    for da in discovered:
        agent = loader.load(da)
        if agent:
            agent_reg.register(
                da.agent_id,
                agent,
                {"model": da.model or best_model_for_purpose("chat") or "deepseek-chat"},
                metadata=da,
                skills=da.skills or [],
                tools=da.tools or [],
                category=da.category or "",
                tags=da.tags or [],
            )

    rt = KernelRuntime(
        agent_manager=agent_mgr,
        skill_manager=skill_mgr,
        execution_store=store,
        workspace_agent_manager=ws_agent_mgr,
    )
    set_kernel_runtime(rt)
    harness = get_harness()
    harness.attach_runtime(rt)


def _svc(rt: Optional[KernelRuntime]):
    store = getattr(rt, "execution_store", None) if rt else None
    return create_conversation_service(store)


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
    scope = normalize_conversation_scope(request.model_dump(exclude_none=True), fallback=current.get("scope") or {})
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
    scope_applied = normalize_conversation_scope(
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
    # Execute via HTTP call to core gateway (instead of direct in-process harness call)
    import os
    import httpx as _httpx
    core_url = os.getenv("AIPLAT_CORE_URL", "http://localhost:8002").rstrip("/")
    exec_body = {"kind": "agent", "target_id": "materials_chat_agent", "payload": payload, "user_id": user_id, "session_id": session_id}
    try:
        async with _httpx.AsyncClient(timeout=300.0) as _client:
            _resp = await _client.post(
                f"{core_url}/api/core/gateway/execute",
                json=exec_body,
                headers={"Content-Type": "application/json"},
            )
            core_result = _resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"core_gateway_failed: {e}")
    if isinstance(core_result, dict):
        resp = dict(core_result)
        # Normalize nested output field
        if resp.get("output") and isinstance(resp["output"], dict):
            resp["answer"] = resp["output"].get("answer", "")
            resp["strategy"] = resp["output"].get("strategy", "")
        resp["ok"] = resp.get("ok", resp.get("status") == "completed")
    else:
        resp = {"ok": False, "status": "failed", "error": str(core_result)}
    resp["session_id"] = session_id
    resp["scope_applied"] = scope_applied
    return resp


@router.post("/conversations/{session_id}/query/stream")
async def query_conversation_stream(session_id: str, request: ConversationQueryRequest, http_request: Request, rt: RuntimeDep = None):
    """Stream conversation query response via Server-Sent Events."""
    from fastapi.responses import StreamingResponse
    import json as _json

    actor = actor_from_http(http_request, request.model_dump())
    tenant_id = str(actor.get("tenant_id") or "default")
    user_id = str(request.user_id or actor.get("actor_id") or "system")
    svc = _svc(rt)
    convo = await svc.get_conversation_session(session_id=session_id)
    scope_applied = normalize_conversation_scope(
        request.scope_override.model_dump(exclude_none=True) if request.scope_override else convo.get("scope") or {},
        fallback=convo.get("scope") or {},
    )
    doc_ids = [str(x).strip() for x in (scope_applied.get("doc_ids") or []) if str(x).strip()]
    wiki_titles = [str(x).strip() for x in (scope_applied.get("wiki_titles") or []) if str(x).strip()]
    collection_id = str(scope_applied.get("collection_id") or "default")
    question = str(request.message or "").strip()

    await svc.append_conversation_user_message(
        tenant_id=tenant_id, session_id=session_id, user_id=user_id, content=question,
    )

    # Retrieve content from Wiki knowledge pages (primary) or KB documents (fallback)
    doc_content = ""
    is_wiki = bool(wiki_titles)
    try:
        if is_wiki:
            from core.api.core_facade import wiki_retrieve
            results = wiki_retrieve(query=question, wiki_titles=wiki_titles if wiki_titles else None, top_k=8)
        else:
            from core.api.facades.kb_facade import kb_retrieve
            results = kb_retrieve(query=question, doc_ids=doc_ids, collection_id=collection_id, tenant_id=tenant_id, top_k=5)
        if results:
            doc_content = "\n\n---\n\n".join(
                f"[{r.get('title', '')}] {r.get('text', '')}" if r.get('title') else r.get('text', '')
                for r in results
            )
    except ImportError:
        pass

    async def _stream():
        if not doc_content:
            yield f"data: {_json.dumps({'error': 'no_document_content', 'done': True})}\n\n"
            return

        try:
            from core.api.core_facade import llm_generate_stream
            full_answer = []
            from core.harness.utils.prompt_loader import _sync_resolve
            system_prompt = _sync_resolve("kb-qa",
                scenario="wiki" if is_wiki else "document",
                documents="", question="",
            ).split("\n\n")[0]
            async for chunk in llm_generate_stream(
                None,
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"知识内容：\n{doc_content[:4000]}\n\n用户问题：{question}\n\n请回答："},
                ],
                model_name=best_model_for_purpose("chat") or "deepseek-chat", temperature=0.3, max_tokens=2000,
            ):
                if chunk:
                    full_answer.append(chunk)
                    yield f"data: {_json.dumps({'text': chunk})}\n\n"

            answer = "".join(full_answer).strip()
            # Save final answer to conversation
            try:
                from core.api.facades.service_facade import normalize_conversation_scope
                await svc.append_conversation_assistant_message(
                    tenant_id=tenant_id, session_id=session_id, user_id=user_id,
                    content=answer, citations=[], turn_summary=f"用户提问：{question}；本轮回答：{answer[:160]}",
                    strategy="stream_retrieve", mode="", intent="fact_lookup",
                    skills_used=["sys_kb_retrieve", "sys_llm_generate_stream"],
                    analysis={}, retrieval_policy={}, answer_strategy={}, run_id="",
                )
            except Exception:
                pass
            yield f"data: {_json.dumps({'done': True, 'answer': answer})}\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'error': str(e), 'done': True})}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")
