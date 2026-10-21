"""Request identity trust decisions for the platform HTTP edge.

Header tenant/actor/role are not credentials. They are accepted only in
explicit dev mode or when the caller presents the internal identity secret.
"""
from __future__ import annotations

import hmac
import os
from typing import Any, Mapping, Optional


def _flag(name: str) -> bool:
    return os.getenv(name, "false").lower() in ("1", "true", "yes", "y")


def header_identity_allowed(presented_secret: str | None) -> bool:
    """True when spoofable identity headers may be trusted.

    ``AIPLAT_PLATFORM_DEV_MODE`` keeps the local management UI path.
    Otherwise ``X-AIPLAT-IDENTITY-SECRET`` must match
    ``AIPLAT_PLATFORM_IDENTITY_SECRET``.
    """
    if _flag("AIPLAT_PLATFORM_DEV_MODE"):
        return True
    expected = os.getenv("AIPLAT_PLATFORM_IDENTITY_SECRET", "").strip()
    got = (presented_secret or "").strip()
    if not expected or not got or len(expected) != len(got):
        return False
    return hmac.compare_digest(got, expected)


def platform_dev_mode() -> bool:
    return _flag("AIPLAT_PLATFORM_DEV_MODE")


_ROLE_HEADER_KEYS = (
    "X-AIPLAT-ACTOR-ROLE",
    "x-aiplat-actor-role",
    "X-AIPLAT-ROLE",
    "x-aiplat-role",
)


def client_role_header(headers: Mapping[str, Any]) -> str:
    """Raw client role claim (spoofable unless gated)."""
    for key in _ROLE_HEADER_KEYS:
        raw = headers.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


def trusted_actor_role(
    headers: Mapping[str, Any],
    *,
    resolved_actor_role: Optional[str] = None,
) -> str:
    """Role for authorization.

    Prefer JWT / API-key / trusted-header identity. Client role headers are
    accepted only when ``header_identity_allowed`` (dev mode or identity secret).
    """
    resolved = (resolved_actor_role or "").strip()
    if resolved:
        return resolved
    if header_identity_allowed(headers.get("X-AIPLAT-IDENTITY-SECRET")):
        return client_role_header(headers)
    return ""


def resolve_request_role(request: Any) -> str:
    """Resolve actor role from a FastAPI Request via platform identity."""
    from api.rest.routes import _resolve_identity

    ident = _resolve_identity(request)
    return trusted_actor_role(
        request.headers,
        resolved_actor_role=getattr(ident, "actor_role", None),
    )
