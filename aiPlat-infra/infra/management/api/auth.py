"""Infra management API token gate.

When ``AIPLAT_INFRA_API_TOKEN`` (or ``AIPLAT_INFRA_API_KEY``) is set, every
route except ``GET /health`` must present the same value via
``Authorization: Bearer …`` or ``X-AIPLAT-INFRA-TOKEN``.

Binding non-loopback without a token is refused in ``run_server`` — that is
the fail-closed half of the P0; this module enforces the token when present.
"""

from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


def infra_api_token() -> Optional[str]:
    tok = (os.getenv("AIPLAT_INFRA_API_TOKEN") or os.getenv("AIPLAT_INFRA_API_KEY") or "").strip()
    return tok or None


def is_loopback_host(host: str) -> bool:
    h = (host or "").strip().lower()
    return h in ("127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1")


def extract_request_token(request: Request) -> Optional[str]:
    header = (request.headers.get("x-aiplat-infra-token") or "").strip()
    if header:
        return header
    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def tokens_match(expected: str, provided: Optional[str]) -> bool:
    if not provided:
        return False
    try:
        return secrets.compare_digest(expected, provided)
    except Exception:
        return False


class InfraTokenMiddleware(BaseHTTPMiddleware):
    """Require infra API token when env token is configured."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path or ""
        if request.method == "GET" and path == "/health":
            return await call_next(request)

        expected = infra_api_token()
        if not expected:
            if os.getenv("AIPLAT_INFRA_REQUIRE_AUTH", "").strip().lower() in (
                "1",
                "true",
                "yes",
                "y",
            ):
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "AIPLAT_INFRA_API_TOKEN required (AIPLAT_INFRA_REQUIRE_AUTH=1)",
                    },
                )
            return await call_next(request)

        if not tokens_match(expected, extract_request_token(request)):
            return JSONResponse(
                status_code=401,
                content={"detail": "invalid or missing infra API token"},
            )
        return await call_next(request)
