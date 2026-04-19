"""
aiPlat-app HTTP API (management-facing)

This service is used by the management console pages under /app/*.
For now it provides a minimal in-memory implementation:
- /health
- /app/channels CRUD + test
- /app/sessions list/get/end
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException

from utils.ids import new_prefixed_id  # type: ignore
from storage import sqlite as app_store  # type: ignore


app = FastAPI(title="aiPlat-app", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "healthy"}


# -------------------- Channels --------------------


@app.get("/app/channels")
async def list_channels(status: Optional[str] = None):
    items = app_store.list_channels(status=status)
    return {"channels": items, "total": len(items)}


@app.post("/app/channels")
async def create_channel(body: Dict[str, Any]):
    cid = str(body.get("id") or new_prefixed_id("ch"))
    ch = {
        "id": cid,
        "name": body.get("name") or cid,
        "type": body.get("type") or "webhook",
        "config": body.get("config") or {},
        "status": body.get("status") or "active",
        "last_active": None,
        "message_count": 0,
        "created_at": "",
        "updated_at": "",
    }
    return app_store.upsert_channel(ch)


@app.get("/app/channels/{channel_id}")
async def get_channel(channel_id: str):
    ch = app_store.get_channel(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="channel_not_found")
    return ch


@app.put("/app/channels/{channel_id}")
async def update_channel(channel_id: str, patch: Dict[str, Any]):
    ch = app_store.get_channel(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="channel_not_found")
    ch.update({k: v for k, v in (patch or {}).items() if v is not None})
    return app_store.upsert_channel(ch)


@app.delete("/app/channels/{channel_id}")
async def delete_channel(channel_id: str):
    app_store.delete_channel(channel_id)
    return {"status": "ok"}


@app.post("/app/channels/{channel_id}/test")
async def test_channel(channel_id: str):
    ch = app_store.get_channel(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="channel_not_found")
    return {"status": "ok", "message": "test_sent"}


# -------------------- Sessions --------------------


@app.get("/app/sessions")
async def list_sessions(status: Optional[str] = None):
    items = app_store.list_sessions(status=status)
    return {"sessions": items, "total": len(items)}


@app.get("/app/sessions/{session_id}")
async def get_session(session_id: str):
    s = app_store.get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="session_not_found")
    return s


@app.post("/app/sessions")
async def create_session(body: Dict[str, Any]):
    sid = str(body.get("id") or new_prefixed_id("sess"))
    s = {
        "id": sid,
        "channel_id": body.get("channel_id"),
        "user_id": body.get("user_id"),
        "status": body.get("status") or "active",
        "created_at": "",
        "last_message_at": None,
        "metadata": body.get("metadata") or {},
    }
    return app_store.upsert_session(s)


@app.post("/app/sessions/{session_id}/end")
async def end_session(session_id: str):
    s = app_store.get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="session_not_found")
    s["status"] = "ended"
    app_store.upsert_session(s)
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("AIPLAT_APP_PORT", "8004")))
