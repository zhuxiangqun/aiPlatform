from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from core.services.execution_store import ExecutionStore


def _scope_hash(scope: Dict[str, Any]) -> str:
    raw = json.dumps(
        {
            "collection_id": str(scope.get("collection_id") or "default"),
            "doc_ids": sorted([str(x) for x in (scope.get("doc_ids") or []) if str(x).strip()]),
            "version": int(scope.get("version") or 1),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return f"sha256:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


def normalize_scope(scope: Optional[Dict[str, Any]], fallback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    base = dict(fallback or {})
    cur = dict(scope or {})
    collection_id = str(cur.get("collection_id") or base.get("collection_id") or "default").strip() or "default"
    doc_ids = [str(x).strip() for x in (cur.get("doc_ids") if cur.get("doc_ids") is not None else base.get("doc_ids") or []) if str(x).strip()]
    version = int(cur.get("version") or base.get("version") or 1)
    out = {
        "collection_id": collection_id,
        "doc_ids": list(dict.fromkeys(doc_ids)),
        "version": version,
    }
    out["scope_hash"] = _scope_hash(out)
    return out


def _metadata_with_scope(metadata: Optional[Dict[str, Any]], *, title: Optional[str], scope: Dict[str, Any], profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    meta = dict(metadata or {})
    if title is not None:
        meta["title"] = str(title)
    meta["conversation_scope"] = normalize_scope(scope)
    if profile is not None:
        meta["conversation_profile"] = dict(profile or {})
    return meta


class ConversationService:
    def __init__(self, store: ExecutionStore):
        self.store = store

    async def create_conversation_session(
        self,
        *,
        tenant_id: str,
        user_id: str,
        title: Optional[str],
        scope: Optional[Dict[str, Any]],
        profile: Optional[Dict[str, Any]],
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_scope = normalize_scope(scope)
        rec = await self.store.create_memory_session(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_type="materials_chat",
            session_type="conversation",
            metadata=_metadata_with_scope({}, title=title or "资料对话", scope=normalized_scope, profile=profile or {}),
            session_id=session_id,
        )
        return await self.get_conversation_session(session_id=str(rec["id"]))

    async def list_conversation_sessions(self, *, tenant_id: str, user_id: Optional[str], limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        rows = await self.store.list_memory_sessions(tenant_id=tenant_id, user_id=user_id, limit=limit, offset=offset)
        items: List[Dict[str, Any]] = []
        for row in rows.get("items") or []:
            if str(row.get("session_type") or "") != "conversation":
                continue
            meta = dict(row.get("metadata") or {})
            items.append(
                {
                    "session_id": str(row.get("id") or ""),
                    "title": str(meta.get("title") or "资料对话"),
                    "scope": normalize_scope(meta.get("conversation_scope") or {}),
                    "updated_at": row.get("updated_at"),
                    "created_at": row.get("created_at"),
                }
            )
        return {"items": items, "total": len(items), "limit": limit, "offset": offset}

    async def get_conversation_session(self, *, session_id: str) -> Dict[str, Any]:
        row = await self.store.get_memory_session(session_id=session_id)
        if not row:
            raise ValueError("conversation_not_found")
        meta = dict(row.get("metadata") or {})
        messages = await self.store.list_memory_messages(session_id=session_id, tenant_id=row.get("tenant_id"), limit=500, offset=0)
        return {
            "session_id": str(row.get("id") or session_id),
            "title": str(meta.get("title") or "资料对话"),
            "scope": normalize_scope(meta.get("conversation_scope") or {}),
            "profile": dict(meta.get("conversation_profile") or {"citation_required": True, "answer_style": "concise", "language": "zh-CN"}),
            "messages": list(messages.get("items") or []),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "tenant_id": row.get("tenant_id"),
            "user_id": row.get("user_id"),
        }

    async def get_conversation_scope(self, *, session_id: str) -> Dict[str, Any]:
        convo = await self.get_conversation_session(session_id=session_id)
        return dict(convo.get("scope") or {})

    async def set_conversation_scope(
        self,
        *,
        session_id: str,
        tenant_id: str,
        user_id: str,
        title: Optional[str],
        scope: Dict[str, Any],
        profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        current = await self.get_conversation_session(session_id=session_id)
        current_scope = normalize_scope(current.get("scope") or {})
        merged = normalize_scope(scope, fallback=current_scope)
        if scope.get("doc_ids") is not None:
            merged["version"] = int(current_scope.get("version") or 1) + 1
            merged["scope_hash"] = _scope_hash(merged)
        await self.store.create_memory_session(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_type="materials_chat",
            session_type="conversation",
            metadata=_metadata_with_scope(
                {
                    "conversation_profile": dict(current.get("profile") or {}),
                },
                title=title or current.get("title") or "资料对话",
                scope=merged,
                profile=profile or current.get("profile") or {},
            ),
            session_id=session_id,
        )
        return merged

    async def append_conversation_user_message(
        self,
        *,
        tenant_id: str,
        session_id: str,
        user_id: str,
        content: str,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self.store.add_memory_message(
            tenant_id=tenant_id,
            session_id=session_id,
            user_id=user_id,
            role="user",
            content=content,
            run_id=run_id,
            metadata={},
        )

    async def append_conversation_assistant_message(
        self,
        *,
        tenant_id: str,
        session_id: str,
        user_id: str,
        content: str,
        citations: Optional[List[Dict[str, Any]]] = None,
        turn_summary: Optional[str] = None,
        strategy: Optional[str] = None,
        mode: Optional[str] = None,
        intent: Optional[str] = None,
        skills_used: Optional[List[str]] = None,
        analysis: Optional[Dict[str, Any]] = None,
        retrieval_policy: Optional[Dict[str, Any]] = None,
        answer_strategy: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self.store.add_memory_message(
            tenant_id=tenant_id,
            session_id=session_id,
            user_id=user_id,
            role="assistant",
            content=content,
            run_id=run_id,
            metadata={
                "citations": list(citations or []),
                "turn_summary": str(turn_summary or "").strip(),
                "strategy": str(strategy or "").strip(),
                "mode": str(mode or "").strip(),
                "intent": str(intent or "").strip(),
                "skills_used": list(skills_used or []),
                "analysis": dict(analysis or {}),
                "retrieval_policy": dict(retrieval_policy or {}),
                "answer_strategy": dict(answer_strategy or {}),
            },
        )

    async def build_conversation_context(self, *, session_id: str, tenant_id: str, limit: int = 12) -> Dict[str, Any]:
        convo = await self.get_conversation_session(session_id=session_id)
        rows = await self.store.list_memory_messages(session_id=session_id, tenant_id=tenant_id, limit=limit, offset=max(0, int((convo.get("messages") or []).__len__()) - limit))
        messages = list(rows.get("items") or [])
        chat_messages: List[Dict[str, str]] = []
        turn_summaries: List[str] = []
        for m in messages:
            chat_messages.append({"role": str(m.get("role") or "user"), "content": str(m.get("content") or "")})
            meta = dict(m.get("metadata") or {})
            ts = str(meta.get("turn_summary") or "").strip()
            if ts:
                turn_summaries.append(ts)
        return {
            "session_id": session_id,
            "title": convo.get("title"),
            "scope": convo.get("scope"),
            "profile": convo.get("profile"),
            "messages": chat_messages,
            "turn_summaries": turn_summaries[-6:],
        }
