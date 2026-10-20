"""Wiki loop trigger / webhook auth — fail closed without a token.

``POST /wiki/loop/webhook`` and trigger CRUD previously accepted any body
with no credential check, so an unauthenticated caller could start pipelines.
Unsigned access is only for explicit ``AIPLAT_WIKI_LOOP_ALLOW_UNSIGNED``.
"""
from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Request


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes", "y")


def wiki_loop_unsigned_allowed() -> bool:
    """True when wiki loop webhook/CRUD may skip the token."""
    return _flag("AIPLAT_WIKI_LOOP_ALLOW_UNSIGNED")


def _extract_token(request: Request) -> str:
    return (
        request.headers.get("x-aiplat-wiki-loop-token")
        or request.headers.get("X-AiPlat-Wiki-Loop-Token")
        or request.headers.get("x-aiplat-api-key")
        or request.headers.get("X-AIPLAT-API-KEY")
        or ""
    ).strip()


def _static_token_ok(got: str) -> bool:
    expected = (os.getenv("AIPLAT_WIKI_LOOP_WEBHOOK_TOKEN") or "").strip()
    if not expected:
        expected = (os.getenv("AIPLAT_API_KEY") or "").strip()
    if not expected or not got or len(expected) != len(got):
        return False
    return hmac.compare_digest(got, expected)


def require_wiki_loop_auth(request: Request) -> None:
    """Require a wiki-loop token unless unsigned access is explicitly allowed.

    Default require=true. ``AIPLAT_WIKI_LOOP_REQUIRE_AUTH=false`` remains an
    escape. Prefer ``AIPLAT_WIKI_LOOP_WEBHOOK_TOKEN``; fall back to
    ``AIPLAT_API_KEY`` so deployments that already set a core key work.
    """
    if wiki_loop_unsigned_allowed():
        return
    if not _flag("AIPLAT_WIKI_LOOP_REQUIRE_AUTH", "true"):
        return

    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="missing wiki loop token")

    if _static_token_ok(token):
        return

    raise HTTPException(status_code=403, detail="invalid wiki loop token")
