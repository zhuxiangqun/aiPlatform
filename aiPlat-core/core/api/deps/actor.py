from __future__ import annotations

import hmac
import os
from typing import Any, Dict, Optional

from fastapi import Request


def _flag(name: str) -> bool:
    return os.getenv(name, "false").lower() in ("1", "true", "yes", "y")


def header_identity_allowed(presented_secret: str | None) -> bool:
    """True when spoofable identity headers / payload context may be trusted.

    Mirrors platform ``auth.request_identity.header_identity_allowed`` so core
    ``rbac_guard`` does not import platform. Same env contract:
    ``AIPLAT_PLATFORM_DEV_MODE`` or matching ``AIPLAT_PLATFORM_IDENTITY_SECRET``.
    """
    if _flag("AIPLAT_PLATFORM_DEV_MODE"):
        return True
    expected = os.getenv("AIPLAT_PLATFORM_IDENTITY_SECRET", "").strip()
    got = (presented_secret or "").strip()
    if not expected or not got or len(expected) != len(got):
        return False
    return hmac.compare_digest(got, expected)


def actor_from_http(http_request: Request, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Extract actor identity for RBAC.

    Client headers and ``payload.context`` role/id/tenant are spoofable.
    Accept them only when ``header_identity_allowed`` (dev mode or identity secret).
    """
    ctx0 = None
    try:
        if isinstance(payload, dict):
            ctx0 = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    except Exception:
        ctx0 = {}
    ctx0 = ctx0 if isinstance(ctx0, dict) else {}

    secret = http_request.headers.get("X-AIPLAT-IDENTITY-SECRET") or http_request.headers.get(
        "x-aiplat-identity-secret"
    )
    if not header_identity_allowed(secret):
        return {"actor_id": None, "actor_role": None, "tenant_id": None}

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
