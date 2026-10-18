"""
Memory Import Routes (P0-b) — Claude Code 会话/记忆导入端点。

POST /platform/memory/import — 解析 Claude Code 会话 JSONL → MemoryManager
（source_tag=claude_import + provenance 溯源）。对标 Codex external_agent_config_migration。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request

from auth.deps import require_auth
from api.schemas_response import StatusResponse

router = APIRouter(prefix="/platform", tags=["memory"])


def _tenant_from_request(request: Request) -> str:
    """Identity comes from platform headers; never invent cross-tenant defaults."""
    tid = (request.headers.get("X-AIPLAT-TENANT-ID") or "").strip()
    return tid or "default"


@router.post("/memory/import", response_model=StatusResponse)
async def import_claude_memories(
    body: Dict[str, Any],
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    """导入 Claude Code 会话 JSONL → MemoryManager。

    body: {"base_path": "~/.claude/projects", "max_sessions": 50}
    返回 {imported, sessions, turns, skipped, errors}。
    """
    from core.api.core_facade import import_claude_memories as _import

    base_path = str(body.get("base_path") or "")
    max_sessions = int(body.get("max_sessions") or 50)
    result = await _import(base_path=base_path, max_sessions=max_sessions)
    return {"status": "ok", "message": "claude_memories_imported", **result}


@router.get("/memory/import/status", response_model=StatusResponse)
async def memory_import_status(_auth: str = Depends(require_auth)) -> Dict[str, Any]:
    """返回记忆导入能力信息（来源路径、上限）。"""
    return {
        "status": "ok",
        "service": "memory-import",
        "sources": ["~/.claude/projects", "~/.claude/transcripts"],
        "max_sessions_per_import": 50,
        "source_tag": "claude_import",
        "ide_capture": "POST /platform/memory/capture",
    }


@router.post("/memory/capture", response_model=StatusResponse)
async def capture_ide_session(
    body: Dict[str, Any],
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    """IDE/Cursor/CC 旁路投递 → Team Brain（可选 Session Wiki）。

    body: {prompt, result?, tools?, success?, tags?, session_id?, write_wiki?, source?}
    """
    from core.api.core_facade import ingest_ide_capture as _ingest

    prompt = str(body.get("prompt") or body.get("title") or "").strip()
    result = str(body.get("result") or body.get("summary") or body.get("content") or "").strip()
    if not prompt and not result:
        return {"status": "error", "message": "prompt_or_result_required"}
    out = _ingest(
        prompt=prompt,
        result=result,
        tools=body.get("tools") if isinstance(body.get("tools"), list) else None,
        success=bool(body.get("success", True)),
        tags=body.get("tags") if isinstance(body.get("tags"), list) else None,
        source=str(body.get("source") or "ide"),
        session_id=str(body.get("session_id") or ""),
        write_wiki=bool(body.get("write_wiki", False)),
    )
    return {"status": "ok" if out.get("ok") else "error", "message": "ide_capture", **out}


@router.get("/memory/archive", response_model=StatusResponse)
async def session_archive(
    request: Request,
    q: str = "",
    limit: int = 3,
    session_id: str = "",
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    """On-demand search of turns archived before compaction. Not the sticky fact list."""
    from core.api.core_facade import query_session_archive as _query

    out = _query(
        q,
        limit=limit,
        session_id=str(session_id or ""),
        tenant_id=_tenant_from_request(request),
    )
    return {"status": "ok", "message": "session_archive", **out}


@router.get("/memory/sticky", response_model=StatusResponse)
async def sticky_memory(
    request: Request,
    max_chars: Optional[int] = None,
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    """User profile + pinned MEMORY.md for Pi / hybrid session start. Shared budget."""
    from core.api.core_facade import sticky_memory_slice as _slice

    out = _slice(max_chars=max_chars, tenant_id=_tenant_from_request(request))
    return {"status": "ok", "message": "sticky_memory", **out}


@router.post("/memory/sticky", response_model=StatusResponse)
async def upsert_sticky_memory(
    request: Request,
    body: Dict[str, Any],
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    """Add or replace a durable pinned fact. Same-key merge when budget is full."""
    from core.api.core_facade import upsert_pinned_memory as _upsert

    out = _upsert(
        str(body.get("content") or ""),
        key=str(body.get("key") or "preference"),
        source=str(body.get("source") or "agent"),
        old_text=str(body.get("old_text") or ""),
        tenant_id=_tenant_from_request(request),
    )
    return {
        "status": "ok" if out.get("ok") else "error",
        "message": "sticky_upsert",
        **out,
    }
