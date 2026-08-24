"""
Memory Import Routes (P0-b) — Claude Code 会话/记忆导入端点。

POST /platform/memory/import — 解析 Claude Code 会话 JSONL → MemoryManager
（source_tag=claude_import + provenance 溯源）。对标 Codex external_agent_config_migration。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends

from auth.deps import require_auth
from api.schemas_response import StatusResponse

router = APIRouter(prefix="/platform", tags=["memory"])


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
    }
