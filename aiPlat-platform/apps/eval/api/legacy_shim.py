"""EVAL_V1 E1 — mark legacy eval mounts as deprecated in favor of /api/platform/apps/eval."""
from __future__ import annotations

import re
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

CANONICAL_PREFIX = "/api/platform/apps/eval"
LEGACY_APPS_PREFIX = "/api/platform/apps"

# Path prefixes that belong to the eval app when mounted under /api/platform/apps (no /eval).
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
        return f"{CANONICAL_PREFIX}/"  # overview migration later
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


class EvalLegacyDeprecationMiddleware(BaseHTTPMiddleware):
    """Attach deprecation headers for legacy eval paths (platform + core kb-eval)."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        response = await call_next(request)
        if is_legacy_eval_path(path) or path.startswith("/api/core/kb-eval"):
            apply_eval_deprecation_headers(response, path)
        elif path.startswith("/api/core/evaluation"):
            apply_eval_deprecation_headers(response, path)
        return response
