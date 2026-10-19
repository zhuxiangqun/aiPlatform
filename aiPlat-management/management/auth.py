"""Management API token gate.

When ``AIPLAT_MANAGEMENT_API_TOKEN`` (or ``AIPLAT_MANAGEMENT_API_KEY``) is set,
every route except ``GET /health`` must present the same value via
``Authorization: Bearer …`` or ``X-AIPLAT-MANAGEMENT-TOKEN``.

Binding non-loopback without a token is refused at process start.

Pure helpers import without FastAPI. The middleware needs Starlette at runtime.
"""

from __future__ import annotations

import os
import secrets
from typing import Any, Optional


def management_api_token() -> Optional[str]:
    tok = (
        os.getenv("AIPLAT_MANAGEMENT_API_TOKEN")
        or os.getenv("AIPLAT_MANAGEMENT_API_KEY")
        or ""
    ).strip()
    return tok or None


def is_loopback_host(host: str) -> bool:
    h = (host or "").strip().lower()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    return h in ("127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1")


def assert_bind_allowed(host: str) -> None:
    """Refuse 0.0.0.0 / public binds unless a management API token is set."""
    if is_loopback_host(host) or management_api_token():
        return
    raise SystemExit(
        "Refusing to bind non-loopback without AIPLAT_MANAGEMENT_API_TOKEN "
        "(or AIPLAT_MANAGEMENT_API_KEY)"
    )


def extract_request_token(request: Any) -> Optional[str]:
    header = (request.headers.get("x-aiplat-management-token") or "").strip()
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
    from starlette.responses import JSONResponse

    _HAS_ASGI = True
except ImportError:  # pragma: no cover - unit env without Starlette
    BaseHTTPMiddleware = object  # type: ignore[misc, assignment]
    JSONResponse = None  # type: ignore[misc, assignment]
    _HAS_ASGI = False


class ManagementTokenMiddleware(BaseHTTPMiddleware):
    """Require the management API token when one is configured."""

    async def dispatch(self, request: Any, call_next) -> Any:
        if not _HAS_ASGI:
            raise RuntimeError("starlette required for ManagementTokenMiddleware")

        path = request.url.path or ""
        if request.method == "GET" and path == "/health":
            return await call_next(request)

        expected = management_api_token()
        if not expected:
            if os.getenv("AIPLAT_MANAGEMENT_REQUIRE_AUTH", "").strip().lower() in (
                "1",
                "true",
                "yes",
                "y",
            ):
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "AIPLAT_MANAGEMENT_API_TOKEN required (AIPLAT_MANAGEMENT_REQUIRE_AUTH=1)",
                    },
                )
            return await call_next(request)

        if not tokens_match(expected, extract_request_token(request)):
            return JSONResponse(
                status_code=401,
                content={"detail": "invalid or missing management API token"},
            )
        return await call_next(request)
