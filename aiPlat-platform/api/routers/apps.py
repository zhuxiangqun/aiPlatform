"""
Apps API router — publish, chat, api, webhook for workflows.
"""
from __future__ import annotations

from api.schemas_response import StatusResponse
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Header, Request

from auth.deps import require_auth
from builder.builder_app_service import AppService

router = APIRouter(prefix="/platform/apps", tags=["apps"])
_svc = AppService()


# ── Manage ──

@router.get("", response_model=StatusResponse)
async def list_apps(_auth: str = Depends(require_auth)):
    return {"apps": await _svc.list(), "total": 0}


@router.get("/{app_id}", response_model=StatusResponse)
async def get_app(app_id: str, _auth: str = Depends(require_auth)):
    app = await _svc.get(app_id)
    if not app:
        raise HTTPException(404, detail="app not found")
    return app


@router.delete("/{app_id}", response_model=StatusResponse)
async def delete_app(app_id: str, _auth: str = Depends(require_auth)):
    await _svc.delete(app_id)
    return {"status": "deleted", "id": app_id}


# ── Create App ──

@router.post("", response_model=StatusResponse)
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


# ── Studio Registration (server-to-server, no auth) ──

@router.post("/register-from-studio", response_model=StatusResponse)
async def register_studio_app(req: Dict[str, Any]):
    """Studio 部署完成后注册应用。由 management studio.py 内部调用。"""
    try:
        app = _svc.register_studio(
            app_id=str(req.get("app_id") or ""),
            name=str(req.get("name") or ""),
            project_id=str(req.get("project_id") or ""),
            app_url=str(req.get("app_url") or ""),
        )
        return app
    except ValueError as e:
        raise HTTPException(400, detail=str(e))


# ── API mode ──

@router.post("/{app_id}/run", response_model=StatusResponse)
async def run_api(app_id: str, req: Dict[str, Any], _auth: str = Depends(require_auth)):
    try:
        return await _svc.run_api(app_id, req)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))


# ── Chat mode ──

@router.post("/{app_id}/chat", response_model=StatusResponse)
async def chat(app_id: str, req: Dict[str, Any], _auth: str = Depends(require_auth)):
    try:
        return await _svc.run_chat(app_id, str(req.get("message") or ""))
    except ValueError as e:
        raise HTTPException(400, detail=str(e))


# ── Webhook mode ──

@router.post("/{app_id}/hook", response_model=StatusResponse)
async def webhook(app_id: str, req: Request, body: Dict[str, Any] = None, x_webhook_secret: str = Header(None, alias="X-Webhook-Secret")):
    try:
        if body is None:
            body = {}
        return await _svc.run_webhook(app_id, str(x_webhook_secret or ""), body)
    except ValueError as e:
        raise HTTPException(403 if "secret" in str(e) else 400, detail=str(e))
