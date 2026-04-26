from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api.routers.gateway import _verify_slack_signature
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.kernel.types import ExecutionRequest
from core.utils.ids import new_prefixed_id

router = APIRouter()


def _store(rt):
    return getattr(rt, "execution_store", None) if rt else None


def _harness(rt):
    if rt is not None and getattr(rt, "harness", None) is not None:
        return getattr(rt, "harness")
    from core.harness.integration import get_harness

    return get_harness()


def _inject_context(payload: Dict[str, Any], http_request: Request, *, entrypoint: str, channel: str) -> Dict[str, Any]:
    ctx = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    ctx = dict(ctx) if isinstance(ctx, dict) else {}
    ctx.setdefault("entrypoint", entrypoint)
    ctx.setdefault("channel", channel)
    tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID") or http_request.headers.get("x-aiplat-tenant-id")
    actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID") or http_request.headers.get("x-aiplat-actor-id")
    actor_role = http_request.headers.get("X-AIPLAT-ACTOR-ROLE") or http_request.headers.get("x-aiplat-actor-role")
    if tenant_id:
        ctx.setdefault("tenant_id", str(tenant_id))
    if actor_id:
        ctx.setdefault("actor_id", str(actor_id))
    if actor_role:
        ctx.setdefault("actor_role", str(actor_role))
    payload["context"] = ctx
    return payload


async def _execute(*, rt, http_request: Request, channel: str, kind: str, target_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    harness = _harness(rt)
    store = _store(rt)
    execution_id = new_prefixed_id("run")
    payload = _inject_context(dict(payload or {}), http_request, entrypoint="channel_adapter", channel=channel)
    req = ExecutionRequest(kind=str(kind), target_id=str(target_id), payload=payload, run_id=execution_id, user_id="admin", session_id="default")
    res = await harness.execute(req)
    # Normalize minimal response
    return {
        "status": "ok" if res.ok else "failed",
        "ok": bool(res.ok),
        "run_id": str(res.run_id or execution_id),
        "trace_id": str(res.trace_id) if res.trace_id else None,
        "error": res.error,
        "result": getattr(res, "payload", None),
        "channel": channel,
    }


@router.post("/channels/webhook/event")
async def webhook_event(request: dict, http_request: Request, rt=Depends(get_kernel_runtime)):
    """
    Generic channel adapter: expects already-normalized envelope.
    Body:
      { "kind": "...", "target_id": "...", "payload": {...} }
    """
    body = request or {}
    kind = str(body.get("kind") or "agent")
    target_id = str(body.get("target_id") or "react_agent")
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    return await _execute(rt=rt, http_request=http_request, channel="webhook", kind=kind, target_id=target_id, payload=payload)


@router.post("/channels/slack/event")
async def slack_event(http_request: Request, rt=Depends(get_kernel_runtime)):
    """
    Slack adapter (official template).
    - Verifies signature when AIPLAT_SLACK_SIGNING_SECRET is set
    - Handles url_verification (challenge)
    - Normalizes message events into the generic gateway payload
    """
    raw = await http_request.body()
    _verify_slack_signature(http_request, raw)
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")

    if isinstance(body, dict) and body.get("type") == "url_verification" and body.get("challenge"):
        return {"challenge": body.get("challenge")}

    event = body.get("event") if isinstance(body, dict) else None
    text = ""
    channel_user_id: Optional[str] = None
    if isinstance(event, dict):
        text = str(event.get("text") or "")
        channel_user_id = str(event.get("user") or "") or None
    if not text:
        # For slash commands/interactions, allow fallback
        text = str(body.get("text") or "")
        channel_user_id = str(body.get("user_id") or "") or None

    kind = str(body.get("kind") or "agent")
    target_id = str(body.get("target_id") or "react_agent")
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {"input": {"task": text}}
    if isinstance(payload, dict):
        inp = payload.get("input") if isinstance(payload.get("input"), dict) else {}
        inp = dict(inp)
        inp.setdefault("task", text)
        payload["input"] = inp
        if channel_user_id:
            ctx0 = payload.get("context") if isinstance(payload.get("context"), dict) else {}
            ctx0 = dict(ctx0)
            ctx0.setdefault("channel_user_id", channel_user_id)
            payload["context"] = ctx0

    return await _execute(rt=rt, http_request=http_request, channel="slack", kind=kind, target_id=target_id, payload=payload)
