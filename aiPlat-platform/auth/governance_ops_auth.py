"""Governance ops auth — fail closed without a token.

``POST /governance/jobs`` can start arbitrary shell commands. Agent-bus
register/send and repo-health scan are also mutating. Unsigned access is
only for explicit ``AIPLAT_GOVERNANCE_ALLOW_UNSIGNED``.
"""
from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Request


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes", "y")


def governance_ops_unsigned_allowed() -> bool:
    """True when governance mutating routes may skip the token."""
    return _flag("AIPLAT_GOVERNANCE_ALLOW_UNSIGNED")


def _extract_token(request: Request) -> str:
    return (
        request.headers.get("x-aiplat-governance-ops-token")
        or request.headers.get("X-AiPlat-Governance-Ops-Token")
        or request.headers.get("x-aiplat-api-key")
        or request.headers.get("X-AIPLAT-API-KEY")
        or ""
    ).strip()


def _static_token_ok(got: str) -> bool:
    expected = (os.getenv("AIPLAT_GOVERNANCE_OPS_TOKEN") or "").strip()
    if not expected:
        expected = (os.getenv("AIPLAT_API_KEY") or "").strip()
    if not expected or not got or len(expected) != len(got):
        return False
    return hmac.compare_digest(got, expected)


def require_governance_ops_auth(request: Request) -> None:
    """Require a governance-ops token unless unsigned access is explicitly allowed.

    Default require=true. ``AIPLAT_GOVERNANCE_OPS_REQUIRE_AUTH=false`` remains an
    escape. Prefer ``AIPLAT_GOVERNANCE_OPS_TOKEN``; fall back to
    ``AIPLAT_API_KEY`` so deployments that already set a platform key work.
    """
    if governance_ops_unsigned_allowed():
        return
    if not _flag("AIPLAT_GOVERNANCE_OPS_REQUIRE_AUTH", "true"):
        return

    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="missing governance ops token")

    if _static_token_ok(token):
        return

    raise HTTPException(status_code=403, detail="invalid governance ops token")
