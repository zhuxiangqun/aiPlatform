"""EVAL_V1 — 308 redirect core /kb-eval (and mark /evaluation) → platform canonical (ARCH v1.2)."""
from __future__ import annotations

from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

CANONICAL_PREFIX = "/api/platform/apps/eval"


def _successor(path: str) -> str:
    if path.startswith("/api/core/kb-eval"):
        rest = path[len("/api/core/kb-eval") :] or "/"
        return f"{CANONICAL_PREFIX}/kb-eval{rest}"
    if path.startswith("/api/core/evaluation"):
        return f"{CANONICAL_PREFIX}/"
    return CANONICAL_PREFIX


class EvalCoreLegacyDeprecationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if path.startswith("/api/core/kb-eval"):
            successor = _successor(path)
            q = request.url.query
            loc = f"{successor}?{q}" if q else successor
            resp = RedirectResponse(url=loc, status_code=308)
            resp.headers["Deprecation"] = "true"
            resp.headers["X-Aiplat-Eval-Canonical-Prefix"] = CANONICAL_PREFIX
            resp.headers["Link"] = f'<{successor}>; rel="successor-version"'
            resp.headers.setdefault(
                "Warning",
                '299 - "EVAL_V1: use /api/platform/apps/eval; this path is a legacy shim"',
            )
            return resp
        response = await call_next(request)
        if path.startswith("/api/core/evaluation"):
            successor = _successor(path)
            response.headers["Deprecation"] = "true"
            response.headers["X-Aiplat-Eval-Canonical-Prefix"] = CANONICAL_PREFIX
            response.headers["Link"] = f'<{successor}>; rel="successor-version"'
            response.headers.setdefault(
                "Warning",
                '299 - "EVAL_V1: use /api/platform/apps/eval; this path is a legacy shim"',
            )
        return response
