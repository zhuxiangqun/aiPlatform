"""Studio app registration auth — fail closed without a token.

``POST /platform/apps/register-from-studio`` previously accepted any body
with no credential check, so an unauthenticated caller could register apps
into the platform catalog. Unsigned access is only for explicit
``AIPLAT_STUDIO_REGISTER_ALLOW_UNSIGNED``.
"""
from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Request


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes", "y")


def studio_register_unsigned_allowed() -> bool:
    """True when studio register may skip the token."""
    return _flag("AIPLAT_STUDIO_REGISTER_ALLOW_UNSIGNED")


def _extract_token(request: Request) -> str:
    return (
        request.headers.get("x-aiplat-studio-register-token")
        or request.headers.get("X-AiPlat-Studio-Register-Token")
        or request.headers.get("x-aiplat-api-key")
        or request.headers.get("X-AIPLAT-API-KEY")
        or ""
    ).strip()


def _static_token_ok(got: str) -> bool:
    expected = (os.getenv("AIPLAT_STUDIO_REGISTER_TOKEN") or "").strip()
    if not expected:
        expected = (os.getenv("AIPLAT_API_KEY") or "").strip()
    if not expected or not got or len(expected) != len(got):
        return False
    return hmac.compare_digest(got, expected)


def require_studio_register_auth(request: Request) -> None:
    """Require a studio-register token unless unsigned access is explicitly allowed.

    Default require=true. ``AIPLAT_STUDIO_REGISTER_REQUIRE_AUTH=false`` remains an
    escape. Prefer ``AIPLAT_STUDIO_REGISTER_TOKEN``; fall back to
    ``AIPLAT_API_KEY`` so deployments that already set a platform key work.
    """
    if studio_register_unsigned_allowed():
        return
    if not _flag("AIPLAT_STUDIO_REGISTER_REQUIRE_AUTH", "true"):
        return

    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="missing studio register token")

    if _static_token_ok(token):
        return

    raise HTTPException(status_code=403, detail="invalid studio register token")
