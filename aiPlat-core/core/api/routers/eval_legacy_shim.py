"""EVAL_V1 E1 — deprecation headers for core /evaluation and /kb-eval legacy paths."""
from __future__ import annotations

from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

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
        response = await call_next(request)
        if path.startswith("/api/core/kb-eval") or path.startswith("/api/core/evaluation"):
            successor = _successor(path)
            response.headers["Deprecation"] = "true"
            response.headers["X-Aiplat-Eval-Canonical-Prefix"] = CANONICAL_PREFIX
            response.headers["Link"] = f'<{successor}>; rel="successor-version"'
            response.headers.setdefault(
                "Warning",
                '299 - "EVAL_V1: use /api/platform/apps/eval; this path is a legacy shim"',
            )
        return response
