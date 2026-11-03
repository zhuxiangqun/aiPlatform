"""EVAL_V1 — legacy eval path redirect table → /api/platform/apps/eval (ARCH v1.2)."""
from __future__ import annotations

import re
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

CANONICAL_PREFIX = "/api/platform/apps/eval"
LEGACY_APPS_PREFIX = "/api/platform/apps"

# Explicit redirect table: flat /apps/{…} → /apps/eval/{…} (no dual business mount).
_LEGACY_EVAL_PREFIXES = (
    f"{LEGACY_APPS_PREFIX}/kb-eval",
    f"{LEGACY_APPS_PREFIX}/code-review-gold",
    f"{LEGACY_APPS_PREFIX}/skill-evals",
    f"{LEGACY_APPS_PREFIX}/prompts/eval",
    f"{LEGACY_APPS_PREFIX}/arena/",
    f"{LEGACY_APPS_PREFIX}/wake-agent/",
)

_RUNS_EVAL_RE = re.compile(
    r"^/api/platform/apps/runs/[^/]+/(evaluate|evaluation|investigate|evidence|state)(/|$)"
)


def is_legacy_eval_path(path: str) -> bool:
    if path.startswith(CANONICAL_PREFIX + "/") or path == CANONICAL_PREFIX:
        return False
    if any(path.startswith(p) for p in _LEGACY_EVAL_PREFIXES):
        return True
    return bool(_RUNS_EVAL_RE.match(path))


def canonical_successor(path: str) -> str:
    if path.startswith(CANONICAL_PREFIX):
        return path
    if path.startswith(LEGACY_APPS_PREFIX + "/"):
        rest = path[len(LEGACY_APPS_PREFIX) :]  # includes leading /
        return f"{CANONICAL_PREFIX}{rest}"
    if path.startswith("/api/core/kb-eval"):
        rest = path[len("/api/core/kb-eval") :] or "/"
        return f"{CANONICAL_PREFIX}/kb-eval{rest}"
    if path.startswith("/api/core/evaluation"):
        return f"{CANONICAL_PREFIX}/"
    return CANONICAL_PREFIX


def apply_eval_deprecation_headers(response: Response, path: str) -> None:
    successor = canonical_successor(path)
    response.headers["Deprecation"] = "true"
    response.headers["X-Aiplat-Eval-Canonical-Prefix"] = CANONICAL_PREFIX
    response.headers["Link"] = f'<{successor}>; rel="successor-version"'
    response.headers.setdefault(
        "Warning",
        '299 - "EVAL_V1: use /api/platform/apps/eval; this path is a legacy shim"',
    )


def _redirect_location(request: Request, successor: str) -> str:
    q = request.url.query
    return f"{successor}?{q}" if q else successor


class EvalLegacyDeprecationMiddleware(BaseHTTPMiddleware):
    """308 redirect legacy flat eval paths; attach Deprecation headers on redirect."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if is_legacy_eval_path(path):
            successor = canonical_successor(path)
            resp = RedirectResponse(
                url=_redirect_location(request, successor), status_code=308
            )
            apply_eval_deprecation_headers(resp, path)
            return resp
        response = await call_next(request)
        if path.startswith("/api/core/kb-eval") or path.startswith(
            "/api/core/evaluation"
        ):
            apply_eval_deprecation_headers(response, path)
        return response
