"""Platform bind / edge token gate.

When ``AIPLAT_PLATFORM_API_TOKEN`` (or ``AIPLAT_API_KEY``) is set, every route
except ``GET /health`` must present it via ``Authorization: Bearer …`` or
``X-AIPLAT-PLATFORM-TOKEN``.

Binding non-loopback without a token is refused at process start.
"""

from __future__ import annotations

import os
import secrets
from typing import Any, Optional


def platform_api_token() -> Optional[str]:
    tok = (
        os.getenv("AIPLAT_PLATFORM_API_TOKEN")
        or os.getenv("AIPLAT_API_KEY")
        or ""
    ).strip()
    return tok or None


def is_loopback_host(host: str) -> bool:
    h = (host or "").strip().lower()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    return h in ("127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1")


def assert_platform_bind_allowed(host: str) -> None:
    """Refuse public binds unless a platform API token is set."""
    if is_loopback_host(host) or platform_api_token():
        return
    raise SystemExit(
        "Refusing to bind non-loopback without AIPLAT_PLATFORM_API_TOKEN "
        "(or AIPLAT_API_KEY)"
    )


def extract_request_token(request: Any) -> Optional[str]:
    header = (request.headers.get("x-aiplat-platform-token") or "").strip()
    if header:
        return header
    # Same header require_auth accepts — keep one credential for Docker.
    api_key = (request.headers.get("x-aiplat-api-key") or "").strip()
    if api_key:
        return api_key
    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def tokens_match(expected: str, provided: Optional[str]) -> bool:
    if not provided or len(provided) != len(expected):
        return False
    return secrets.compare_digest(expected, provided)


try:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    _HAS_ASGI = True
except ImportError:  # pragma: no cover
    BaseHTTPMiddleware = object  # type: ignore[misc, assignment]
    JSONResponse = None  # type: ignore[misc, assignment]
    _HAS_ASGI = False


class PlatformTokenMiddleware(BaseHTTPMiddleware):
    """Require the platform API token when one is configured."""

    async def dispatch(self, request: Any, call_next) -> Any:
        if not _HAS_ASGI:
            raise RuntimeError("starlette required for PlatformTokenMiddleware")
        path = request.url.path or ""
        if request.method == "GET" and path.rstrip("/") in ("/health",):
            return await call_next(request)
        expected = platform_api_token()
        if not expected:
            return await call_next(request)
        if not tokens_match(expected, extract_request_token(request)):
            return JSONResponse(
                status_code=401,
                content={"detail": "invalid or missing platform API token"},
            )
        return await call_next(request)
