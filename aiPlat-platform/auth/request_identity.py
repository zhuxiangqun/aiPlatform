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

    Args:
        presented_secret: presented_secret 参数。
    """
    if _flag("AIPLAT_PLATFORM_DEV_MODE"):
        return True
    expected = os.getenv("AIPLAT_PLATFORM_IDENTITY_SECRET", "").strip()
    got = (presented_secret or "").strip()
    if not expected or not got or len(expected) != len(got):
        return False
    return hmac.compare_digest(got, expected)


def platform_dev_mode() -> bool:
    """platform_dev_mode。
    """
    return _flag("AIPLAT_PLATFORM_DEV_MODE")


def service_to_core_identity_headers(
    *,
    tenant_id: str,
    actor_id: str,
    request_id: Optional[str] = None,
    actor_role: Optional[str] = None,
    scopes: Optional[list[str]] = None,
    content_type: str = "application/json",
) -> dict[str, str]:
    """Build platform→core identity headers (service-to-service).

    Args:
        tenant_id: 租户 ID。
        actor_id: actor 标识。
        request_id: request 标识。
        actor_role: actor_role 参数。
        scopes: scopes 参数。
        content_type: content_type 参数。
    """
    headers: dict[str, str] = {
        "Content-Type": content_type,
        "X-AIPLAT-TENANT-ID": str(tenant_id),
        "X-AIPLAT-ACTOR-ID": str(actor_id),
    }
    if request_id:
        headers["X-AIPLAT-REQUEST-ID"] = str(request_id)
    if actor_role:
        headers["X-AIPLAT-ACTOR-ROLE"] = str(actor_role)
    if scopes:
        headers["X-AIPLAT-SCOPES"] = ",".join(str(s) for s in scopes if s)
    secret = os.getenv("AIPLAT_PLATFORM_IDENTITY_SECRET", "").strip()
    if secret:
        headers["X-AIPLAT-IDENTITY-SECRET"] = secret
    return headers


_ROLE_HEADER_KEYS = (
    "X-AIPLAT-ACTOR-ROLE",
    "x-aiplat-actor-role",
    "X-AIPLAT-ROLE",
    "x-aiplat-role",
)


def client_role_header(headers: Mapping[str, Any]) -> str:
    """Raw client role claim (spoofable unless gated).

    Args:
        headers: headers 参数。
    """
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

    Args:
        headers: headers 参数。
        resolved_actor_role: resolved_actor_role 参数。
    """
    resolved = (resolved_actor_role or "").strip()
    if resolved:
        return resolved
    if header_identity_allowed(headers.get("X-AIPLAT-IDENTITY-SECRET")):
        return client_role_header(headers)
    return ""


def resolve_request_role(request: Any) -> str:
    """Resolve actor role from a FastAPI Request via platform identity.

    Args:
        request: FastAPI Request。
    """
    from api.rest.routes import _resolve_identity

    ident = _resolve_identity(request)
    return trusted_actor_role(
        request.headers,
        resolved_actor_role=getattr(ident, "actor_role", None),
    )
