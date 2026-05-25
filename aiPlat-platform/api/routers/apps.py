"""
Apps API router — publish, chat, api, webhook for workflows.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Header, Request

from auth.deps import require_auth
from builder.builder_app_service import AppService

router = APIRouter(prefix="/platform/apps", tags=["apps"])
_svc = AppService()


# ── Manage ──

@router.get("")
async def list_apps(_auth: str = Depends(require_auth)):
    return {"apps": await _svc.list(), "total": 0}


@router.get("/{app_id}")
async def get_app(app_id: str, _auth: str = Depends(require_auth)):
    app = await _svc.get(app_id)
    if not app:
        raise HTTPException(404, detail="app not found")
    return app


@router.delete("/{app_id}")
async def delete_app(app_id: str, _auth: str = Depends(require_auth)):
    await _svc.delete(app_id)
    return {"status": "deleted", "id": app_id}


# ── Create App ──

@router.post("")
async def create_app(req: Dict[str, Any], _auth: str = Depends(require_auth)):
    try:
        app = await _svc.publish(
            workflow_id=str(req.get("workflow_id") or req.get("capability_id") or ""),
            name=str(req.get("name") or ""),
            mode=str(req.get("mode") or "chat"),
            description=str(req.get("description") or ""),
        )
        return app
    except ValueError as e:
        raise HTTPException(400, detail=str(e))


# ── API mode ──

@router.post("/{app_id}/run")
async def run_api(app_id: str, req: Dict[str, Any], _auth: str = Depends(require_auth)):
    try:
        return await _svc.run_api(app_id, req)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))


# ── Chat mode ──

@router.post("/{app_id}/chat")
async def chat(app_id: str, req: Dict[str, Any], _auth: str = Depends(require_auth)):
    try:
        return await _svc.run_chat(app_id, str(req.get("message") or ""))
    except ValueError as e:
        raise HTTPException(400, detail=str(e))


# ── Webhook mode ──

@router.post("/{app_id}/hook")
async def webhook(app_id: str, req: Request, body: Dict[str, Any] = None, x_webhook_secret: str = Header(None, alias="X-Webhook-Secret")):
    try:
        if body is None:
            body = {}
        return await _svc.run_webhook(app_id, str(x_webhook_secret or ""), body)
    except ValueError as e:
        raise HTTPException(403 if "secret" in str(e) else 400, detail=str(e))
