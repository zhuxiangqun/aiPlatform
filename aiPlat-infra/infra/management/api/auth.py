"""Infra management API token gate.

When ``AIPLAT_INFRA_API_TOKEN`` (or ``AIPLAT_INFRA_API_KEY``) is set, every
route except ``GET /health`` must present the same value via
``Authorization: Bearer …`` or ``X-AIPLAT-INFRA-TOKEN``.

Binding non-loopback without a token is refused in ``run_server`` — that is
the fail-closed half of the P0; this module enforces the token when present.

Pure helpers here must import without FastAPI (infra unit CI may omit it).
The middleware itself requires FastAPI/Starlette at runtime.
"""

from __future__ import annotations

import os
import secrets
from typing import Any, Optional


def infra_api_token() -> Optional[str]:
    tok = (os.getenv("AIPLAT_INFRA_API_TOKEN") or os.getenv("AIPLAT_INFRA_API_KEY") or "").strip()
    return tok or None


def is_loopback_host(host: str) -> bool:
    h = (host or "").strip().lower()
    return h in ("127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1")


def extract_request_token(request: Any) -> Optional[str]:
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


try:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse, Response

    _HAS_ASGI = True
except ImportError:  # pragma: no cover - CI unit env without FastAPI/Starlette
    BaseHTTPMiddleware = object  # type: ignore[misc, assignment]
    JSONResponse = None  # type: ignore[misc, assignment]
    Response = Any  # type: ignore[misc, assignment]
    _HAS_ASGI = False


class InfraTokenMiddleware(BaseHTTPMiddleware):
    """Require infra API token when env token is configured."""

    async def dispatch(self, request: Any, call_next) -> Any:
        if not _HAS_ASGI:
            raise RuntimeError("fastapi/starlette required for InfraTokenMiddleware")

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
