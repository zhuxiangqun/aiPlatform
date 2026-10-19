"""App static host token gate.

When ``AIPLAT_APP_API_TOKEN`` is set, every route except ``GET /health`` must
present it via ``Authorization: Bearer …`` or ``X-AIPLAT-APP-TOKEN``.

Binding non-loopback without a token is refused at process start.
"""

from __future__ import annotations

import os
import secrets
from typing import Any, Optional


def app_api_token() -> Optional[str]:
    tok = (os.getenv("AIPLAT_APP_API_TOKEN") or "").strip()
    return tok or None


def is_loopback_host(host: str) -> bool:
    h = (host or "").strip().lower()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    return h in ("127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1")


def assert_app_bind_allowed(host: str) -> None:
    """Refuse public binds unless an app API token is set."""
    if is_loopback_host(host) or app_api_token():
        return
    raise SystemExit(
        "Refusing to bind non-loopback without AIPLAT_APP_API_TOKEN"
    )


def extract_request_token(request: Any) -> Optional[str]:
    header = (request.headers.get("x-aiplat-app-token") or "").strip()
    if header:
        return header
    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def tokens_match(expected: str, provided: Optional[str]) -> bool:
    if not provided or len(provided) != len(expected):
        return False
    return secrets.compare_digest(expected, provided)


def channel_unsigned_allowed() -> bool:
    return os.getenv("AIPLAT_CHANNEL_ALLOW_UNSIGNED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
    )


try:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    _HAS_ASGI = True
except ImportError:  # pragma: no cover
    BaseHTTPMiddleware = object  # type: ignore[misc, assignment]
    JSONResponse = None  # type: ignore[misc, assignment]
    _HAS_ASGI = False


class AppTokenMiddleware(BaseHTTPMiddleware):
    """Require the app API token when one is configured."""

    async def dispatch(self, request: Any, call_next) -> Any:
        if not _HAS_ASGI:
            raise RuntimeError("starlette required for AppTokenMiddleware")
        path = request.url.path or ""
        if request.method == "GET" and path == "/health":
            return await call_next(request)
        expected = app_api_token()
        if not expected:
            return await call_next(request)
        if not tokens_match(expected, extract_request_token(request)):
            return JSONResponse(
                status_code=401,
                content={"detail": "invalid or missing app API token"},
            )
        return await call_next(request)
