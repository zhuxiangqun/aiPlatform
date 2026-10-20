"""Gateway edge auth — fail closed without a token.

``AIPLAT_GATEWAY_REQUIRE_AUTH`` historically defaulted to off, so
``POST /platform/gateway/webhook/message`` and ``/execute`` accepted any body.
Unsigned access is only for explicit allow-list / platform dev mode.
"""
from __future__ import annotations

import hmac
import os
from typing import Any, Optional

from fastapi import HTTPException, Request


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes", "y")


def gateway_unsigned_allowed() -> bool:
    """True when gateway execute/webhook may skip the gateway token."""
    if _flag("AIPLAT_GATEWAY_ALLOW_UNSIGNED"):
        return True
    try:
        from auth.request_identity import platform_dev_mode

        return platform_dev_mode()
    except Exception:
        return False


def _extract_gateway_token(request: Request) -> str:
    return (
        request.headers.get("x-aiplat-gateway-token")
        or request.headers.get("X-AiPlat-Gateway-Token")
        or ""
    ).strip()


def _static_token_ok(got: str) -> bool:
    expected = (os.getenv("AIPLAT_GATEWAY_TOKEN") or "").strip()
    if not expected or not got or len(expected) != len(got):
        return False
    return hmac.compare_digest(got, expected)


async def require_gateway_execute_auth(
    request: Request,
    *,
    store: Any = None,
) -> None:
    """Require a gateway token unless unsigned access is explicitly allowed."""
    if gateway_unsigned_allowed():
        return
    # Default require=true — old AIPLAT_GATEWAY_REQUIRE_AUTH=false remains an escape.
    if not _flag("AIPLAT_GATEWAY_REQUIRE_AUTH", "true"):
        return

    token = _extract_gateway_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="missing gateway token")

    if _static_token_ok(token):
        return

    if store is not None:
        try:
            if (await store.validate_gateway_token(token=token)) is not None:
                return
        except Exception as e:
            import logging

            logging.getLogger("aiplat.platform.gateway").warning(
                "gateway token store validation failed: %s", e
            )

    raise HTTPException(status_code=403, detail="invalid gateway token")


def require_gateway_admin(request: Request) -> None:
    """Mutating gateway admin routes need AIPLAT_GATEWAY_ADMIN_TOKEN (or unsigned allow)."""
    if gateway_unsigned_allowed():
        return
    expected = (os.getenv("AIPLAT_GATEWAY_ADMIN_TOKEN") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="gateway admin token not configured",
        )
    got = (
        request.headers.get("x-aiplat-admin-token")
        or request.headers.get("X-AiPlat-Admin-Token")
        or ""
    ).strip()
    if not got or len(got) != len(expected) or not hmac.compare_digest(got, expected):
        raise HTTPException(status_code=403, detail="admin token required")
