"""
Platform Channels and Sessions routes — management console CRUD.

Migrated from aiPlat-app/api/rest/routes.py per architecture contract:
app layer must not run its own HTTP server (docs/index.md §Layer 3).
Channels/sessions management belongs in platform layer.
"""

from __future__ import annotations

from api.schemas_response import StatusResponse
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, Depends, HTTPException

from auth.deps import require_auth

router = APIRouter(prefix="/platform", tags=["channels"])

_channels: Dict[str, Dict[str, Any]] = {}
_sessions: Dict[str, Dict[str, Any]] = {}


def _now() -> float:
    import time
    return time.time()


# ── Channels ─────────────────────────────────────────────────────


@router.get("/channels", response_model=StatusResponse)
async def list_channels(status: Optional[str] = None, _auth: str = Depends(require_auth)):
    items = list(_channels.values())
    if status:
        items = [c for c in items if c.get("status") == status]
    items = sorted(items, key=lambda c: c.get("updated_at", 0), reverse=True)
    return {"channels": items, "total": len(items)}


@router.post("/channels", response_model=StatusResponse)
async def create_channel(body: Dict[str, Any], _auth: str = Depends(require_auth)):
    cid = str(body.get("id") or body.get("name") or "")
    if not cid:
        from core.utils.ids import new_prefixed_id
        cid = new_prefixed_id("ch")
    now = _now()
    ch: Dict[str, Any] = {
        "id": cid,
        "name": body.get("name") or cid,
        "type": body.get("type") or "webhook",
        "config": body.get("config") or {},
        "channel_user_id": body.get("channel_user_id"),
        "status": body.get("status") or "active",
        "last_active": body.get("last_active"),
        "message_count": body.get("message_count", 0),
        "created_at": now,
        "updated_at": now,
    }
    _channels[cid] = ch
    return ch


@router.get("/channels/{channel_id}", response_model=StatusResponse)
async def get_channel(channel_id: str, _auth: str = Depends(require_auth)):
    ch = _channels.get(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="channel_not_found")
    return ch


@router.put("/channels/{channel_id}", response_model=StatusResponse)
async def update_channel(channel_id: str, patch: Dict[str, Any], _auth: str = Depends(require_auth)):
    ch = _channels.get(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="channel_not_found")
    ch.update({k: v for k, v in (patch or {}).items() if v is not None})
    ch["updated_at"] = _now()
    return ch


@router.delete("/channels/{channel_id}", response_model=StatusResponse)
async def delete_channel(channel_id: str, _auth: str = Depends(require_auth)):
    _channels.pop(channel_id, None)
    return {"status": "ok"}


@router.post("/channels/{channel_id}/test", response_model=StatusResponse)
async def test_channel(channel_id: str, _auth: str = Depends(require_auth)):
    ch = _channels.get(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="channel_not_found")
    return {"status": "ok", "message": "test_sent"}


# ── Sessions ─────────────────────────────────────────────────────


@router.get("/sessions", response_model=StatusResponse)
async def list_sessions(status: Optional[str] = None, _auth: str = Depends(require_auth)):
    items = list(_sessions.values())
    if status:
        items = [s for s in items if s.get("status") == status]
    items = sorted(items, key=lambda s: s.get("updated_at", 0), reverse=True)
    return {"sessions": items, "total": len(items)}


@router.get("/sessions/{session_id}", response_model=StatusResponse)
async def get_session(session_id: str, _auth: str = Depends(require_auth)):
    s = _sessions.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="session_not_found")
    return s


@router.post("/sessions", response_model=StatusResponse)
async def create_session(body: Dict[str, Any], _auth: str = Depends(require_auth)):
    sid = str(body.get("id") or "")
    if not sid:
        from core.utils.ids import new_prefixed_id
        sid = new_prefixed_id("sess")
    now = _now()
    s: Dict[str, Any] = {
        "id": sid,
        "channel_id": body.get("channel_id"),
        "user_id": body.get("user_id"),
        "status": body.get("status") or "active",
        "created_at": now,
        "last_message_at": body.get("last_message_at"),
        "metadata": body.get("metadata") or {},
        "updated_at": now,
    }
    _sessions[sid] = s
    return s


@router.post("/sessions/{session_id}/end", response_model=StatusResponse)
async def end_session(session_id: str, _auth: str = Depends(require_auth)):
    s = _sessions.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="session_not_found")
    s["status"] = "ended"
    s["updated_at"] = _now()
    return {"status": "ok"}
