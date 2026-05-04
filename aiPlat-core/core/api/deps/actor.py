from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Request


def actor_from_http(http_request: Request, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ctx0 = None
    try:
        if isinstance(payload, dict):
            ctx0 = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    except Exception:
        ctx0 = {}
    ctx0 = ctx0 if isinstance(ctx0, dict) else {}

    actor_id = (
        (ctx0.get("actor_id") if isinstance(ctx0, dict) else None)
        or http_request.headers.get("X-AIPLAT-ACTOR-ID")
        or http_request.headers.get("x-aiplat-actor-id")
        or (payload.get("user_id") if isinstance(payload, dict) else None)
    )
    actor_role = (
        (ctx0.get("actor_role") if isinstance(ctx0, dict) else None)
        or http_request.headers.get("X-AIPLAT-ACTOR-ROLE")
        or http_request.headers.get("x-aiplat-actor-role")
    )
    tenant_id = (
        (ctx0.get("tenant_id") if isinstance(ctx0, dict) else None)
        or http_request.headers.get("X-AIPLAT-TENANT-ID")
        or http_request.headers.get("x-aiplat-tenant-id")
    )
    return {"actor_id": actor_id, "actor_role": actor_role, "tenant_id": tenant_id}

