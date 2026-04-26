from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api.deps.rbac import actor_from_http
from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime
from core.schemas import (
    LongTermMemoryAddRequest,
    LongTermMemorySearchRequest,
    MessageCreateRequest,
    SearchRequest,
    SessionCreateRequest,
)

router = APIRouter()

RuntimeDep = Optional[KernelRuntime]


def _store(rt: RuntimeDep):
    return getattr(rt, "execution_store", None) if rt else None


def _memory_mgr(rt: RuntimeDep):
    return getattr(rt, "memory_manager", None) if rt else None


# ==================== Memory Management ====================


@router.get("/memory/sessions")
async def list_sessions(http_request: Request, limit: int = 100, offset: int = 0, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """List memory sessions"""
    store = _store(rt)
    if store:
        tenant_id = None
        try:
            tenant_id = actor_from_http(http_request, None).get("tenant_id")
        except Exception:
            tenant_id = None
        res = await store.list_memory_sessions(tenant_id=str(tenant_id) if tenant_id else None, limit=limit, offset=offset)
        out = []
        for s in res.get("items") or []:
            out.append(
                {
                    "session_id": s.get("id"),
                    "tenant_id": s.get("tenant_id"),
                    "metadata": s.get("metadata") or {},
                    "created_at": s.get("created_at"),
                    "updated_at": s.get("updated_at"),
                    "message_count": s.get("message_count") or 0,
                }
            )
        return {"sessions": out, "total": int(res.get("total") or 0)}

    mm = _memory_mgr(rt)
    if not mm:
        raise HTTPException(status_code=503, detail="MemoryManager not initialized")
    sessions = await mm.list_sessions(limit=limit, offset=offset)
    result = []
    for s in sessions:
        result.append(
            {
                "session_id": s.id,
                "metadata": s.metadata,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.last_activity.isoformat() if s.last_activity else None,
                "message_count": s.message_count,
            }
        )
    counts = mm.get_session_count()
    return {"sessions": result, "total": counts["total"]}


@router.post("/memory/sessions")
async def create_session(request: SessionCreateRequest, http_request: Request, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Create memory session"""
    meta = request.metadata or {}
    store = _store(rt)
    if store:
        actor0 = actor_from_http(http_request, {"context": meta} if isinstance(meta, dict) else None)
        tid = actor0.get("tenant_id")
        uid = meta.get("user_id") if isinstance(meta, dict) else None
        if not uid:
            uid = actor0.get("actor_id") or "system"
        if isinstance(meta, dict):
            meta.setdefault("tenant_id", tid)
            meta.setdefault("actor_id", actor0.get("actor_id"))
            meta.setdefault("actor_role", actor0.get("actor_role"))
        session = await store.create_memory_session(
            tenant_id=str(tid) if tid else None,
            user_id=str(uid),
            agent_type=str(meta.get("agent_type", "default")),
            session_type=str(meta.get("session_type", "session")),
            metadata=meta,
            session_id=request.session_id,
        )
        return {"session_id": session.get("id"), "status": "created"}

    mm = _memory_mgr(rt)
    if not mm:
        raise HTTPException(status_code=503, detail="MemoryManager not initialized")
    session = await mm.create_session(
        agent_type=meta.get("agent_type", "default"),
        user_id=meta.get("user_id", "system"),
        session_type=meta.get("session_type", "short_term"),
        metadata=meta,
    )
    return {"session_id": session.id, "status": "created"}


@router.get("/memory/sessions/{session_id}")
async def get_session(session_id: str, http_request: Request, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Get session details"""
    store = _store(rt)
    if store:
        actor0 = actor_from_http(http_request, None)
        tid = actor0.get("tenant_id")
        session = await store.get_memory_session(session_id=session_id)
        if not session or (tid and str(session.get("tenant_id") or "") != str(tid)):
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        msgs = await store.list_memory_messages(session_id=session_id, tenant_id=str(tid) if tid else None, limit=200, offset=0)
        return {
            "session_id": session_id,
            "messages": [
                {
                    "role": m.get("role"),
                    "content": m.get("content"),
                    "timestamp": m.get("created_at"),
                    "source_run_id": m.get("source_run_id"),
                    "run_id": m.get("run_id"),
                    "sensitivity": m.get("sensitivity"),
                }
                for m in (msgs.get("items") or [])
            ],
            "metadata": session.get("metadata") or {},
            "message_count": int(msgs.get("total") or 0),
            "tenant_id": session.get("tenant_id"),
        }

    mm = _memory_mgr(rt)
    if not mm:
        raise HTTPException(status_code=503, detail="MemoryManager not initialized")
    session = await mm.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    messages = await mm.get_messages(session_id)
    return {
        "session_id": session_id,
        "messages": [{"role": m.role, "content": m.content, "timestamp": m.created_at.isoformat() if m.created_at else None} for m in messages],
        "metadata": session.metadata,
        "message_count": len(messages),
    }


@router.delete("/memory/sessions/{session_id}")
async def delete_session(session_id: str, http_request: Request, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Delete session"""
    store = _store(rt)
    if store:
        actor0 = actor_from_http(http_request, None)
        tid = actor0.get("tenant_id")
        session = await store.get_memory_session(session_id=session_id)
        if not session or (tid and str(session.get("tenant_id") or "") != str(tid)):
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        success = await store.delete_memory_session(session_id=session_id)
    else:
        mm = _memory_mgr(rt)
        if not mm:
            raise HTTPException(status_code=503, detail="MemoryManager not initialized")
        success = await mm.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return {"status": "deleted", "session_id": session_id}


@router.get("/memory/sessions/{session_id}/context")
async def get_session_context(session_id: str, http_request: Request, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Get session context"""
    store = _store(rt)
    if store:
        actor0 = actor_from_http(http_request, None)
        tid = actor0.get("tenant_id")
        session = await store.get_memory_session(session_id=session_id)
        if not session or (tid and str(session.get("tenant_id") or "") != str(tid)):
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        msgs = await store.list_memory_messages(session_id=session_id, tenant_id=str(tid) if tid else None, limit=200, offset=0)
        return {"session_id": session_id, "context": {"messages": msgs.get("items") or [], "message_count": int(msgs.get("total") or 0)}}

    mm = _memory_mgr(rt)
    if not mm:
        raise HTTPException(status_code=503, detail="MemoryManager not initialized")
    context = await mm.get_context(session_id)
    if not context:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return {"session_id": session_id, "context": {"messages": context.get("messages", []), "message_count": len(context.get("messages", []))}}


@router.post("/memory/sessions/{session_id}/messages")
async def add_message(session_id: str, request: MessageCreateRequest, http_request: Request, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Add message to session"""
    store = _store(rt)
    if store:
        actor0 = actor_from_http(http_request, None)
        tid = actor0.get("tenant_id")
        session = await store.get_memory_session(session_id=session_id)
        if not session or (tid and str(session.get("tenant_id") or "") != str(tid)):
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        msg = await store.add_memory_message(
            tenant_id=str(tid) if tid else None,
            session_id=session_id,
            user_id=str(actor0.get("actor_id") or session.get("user_id") or "system"),
            role=request.role,
            content=request.content,
            metadata=None,
        )
        return {"status": "added", "message": {"role": msg.get("role"), "content": msg.get("content"), "timestamp": msg.get("created_at")}}

    mm = _memory_mgr(rt)
    if not mm:
        raise HTTPException(status_code=503, detail="MemoryManager not initialized")
    session = await mm.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    message = await mm.add_message(session_id=session_id, role=request.role, content=request.content, metadata=request.metadata)
    return {"status": "added", "message": {"role": message.role, "content": message.content, "timestamp": message.created_at.isoformat() if message.created_at else None}}


@router.post("/memory/search")
async def search_memory(request: SearchRequest, http_request: Request, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Search memory"""
    store = _store(rt)
    if store:
        actor0 = actor_from_http(http_request, None)
        tid = actor0.get("tenant_id")
        res = await store.search_memory_messages(
            query=request.query,
            user_id=None,
            tenant_id=str(tid) if tid else None,
            limit=int(request.limit or 10),
            offset=0,
        )
        return {"results": res.get("items") or [], "total": int(res.get("total") or 0)}

    mm = _memory_mgr(rt)
    if not mm:
        raise HTTPException(status_code=503, detail="MemoryManager not initialized")
    results = await mm.search_memory(request.query, request.limit)
    return {"results": results, "total": len(results)}


@router.get("/memory/pins")
async def list_memory_pins(http_request: Request, session_id: Optional[str] = None, limit: int = 100, offset: int = 0, rt: RuntimeDep = Depends(get_kernel_runtime)):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    tenant_id = None
    try:
        tenant_id = actor_from_http(http_request, None).get("tenant_id")
    except Exception:
        tenant_id = None
    return await store.list_memory_pins(tenant_id=str(tenant_id) if tenant_id else None, session_id=session_id, limit=limit, offset=offset)


@router.post("/memory/pins")
async def pin_memory(request: dict, http_request: Request, rt: RuntimeDep = Depends(get_kernel_runtime)):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    actor0 = actor_from_http(http_request, request if isinstance(request, dict) else None)
    tenant_id = actor0.get("tenant_id")
    session_id = (request or {}).get("session_id")
    message_id = (request or {}).get("message_id")
    if not session_id or not message_id:
        raise HTTPException(status_code=400, detail="session_id and message_id are required")
    note = (request or {}).get("note")
    rec = await store.pin_memory_message(
        tenant_id=str(tenant_id) if tenant_id else None,
        session_id=str(session_id),
        message_id=str(message_id),
        created_by=str(actor0.get("actor_id") or "system"),
        note=str(note) if note else None,
    )
    return {"status": "pinned", "pin": rec}


@router.delete("/memory/pins/{message_id}")
async def unpin_memory(message_id: str, http_request: Request, rt: RuntimeDep = Depends(get_kernel_runtime)):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    actor0 = actor_from_http(http_request, None)
    tenant_id = actor0.get("tenant_id")
    ok = await store.unpin_memory_message(tenant_id=str(tenant_id) if tenant_id else None, message_id=str(message_id))
    if not ok:
        raise HTTPException(status_code=404, detail="pin_not_found")
    return {"status": "unpinned", "message_id": str(message_id)}


@router.get("/memory/stats")
async def get_memory_stats(rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Get memory statistics"""
    mm = _memory_mgr(rt)
    if not mm:
        raise HTTPException(status_code=503, detail="MemoryManager not initialized")
    stats = await mm.get_stats()
    counts = mm.get_session_count()
    return {
        "total_sessions": stats.total_sessions,
        "active_sessions": stats.active_sessions,
        "idle_sessions": stats.idle_sessions,
        "ended_sessions": stats.ended_sessions,
        "total_messages": stats.total_messages,
        "storage_size_mb": stats.storage_size_mb,
        "today_queries": stats.today_queries,
    }


@router.post("/memory/cleanup")
async def cleanup_memory(request: dict, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Cleanup memory"""
    mm = _memory_mgr(rt)
    if not mm:
        raise HTTPException(status_code=503, detail="MemoryManager not initialized")
    max_messages = request.get("max_messages", 100)
    cleaned = await mm.cleanup_memory(max_messages)
    return {"status": "cleaned", "sessions_cleaned": cleaned}


@router.get("/memory/export")
async def export_memory(rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Export memory data"""
    mm = _memory_mgr(rt)
    if not mm:
        raise HTTPException(status_code=503, detail="MemoryManager not initialized")
    counts = mm.get_session_count()
    stats = await mm.get_stats()
    return {
        "total_sessions": counts["total"],
        "stats": {"active": counts["active"], "idle": counts["idle"], "ended": counts["ended"], "total_messages": stats.total_messages},
    }


@router.post("/memory/import")
async def import_memory(request: dict, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Import memory data"""
    mm = _memory_mgr(rt)
    if not mm:
        raise HTTPException(status_code=503, detail="MemoryManager not initialized")
    sessions = request.get("sessions", [])
    imported = 0
    for s in sessions:
        agent_type = s.get("agent_type", "default")
        user_id = s.get("user_id", "system")
        await mm.create_session(agent_type=agent_type, user_id=user_id, metadata=s.get("metadata"))
        imported += 1
    return {"status": "imported", "sessions_imported": imported}


# ==================== Long-term Memory ====================


@router.post("/memory/longterm")
async def add_long_term_memory(request: LongTermMemoryAddRequest, rt: RuntimeDep = Depends(get_kernel_runtime)):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    # 保持与 legacy server.py 一致：透传 key，并直接返回 ExecutionStore 的结果（若有）
    return await store.add_long_term_memory(
        user_id=request.user_id or "system",
        key=request.key,
        content=request.content,
        metadata=request.metadata or {},
    )


@router.post("/memory/longterm/search")
async def search_long_term_memory(request: LongTermMemorySearchRequest, rt: RuntimeDep = Depends(get_kernel_runtime)):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    items = await store.search_long_term_memory(
        user_id=request.user_id or "system",
        query=request.query,
        limit=request.limit,
    )
    return {"items": items, "total": len(items)}
