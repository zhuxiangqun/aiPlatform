"""EVAL A3-local — optional proxy to standalone eval service.

When AIPLAT_EVAL_SERVICE_URL is set, selected /store routes forward to :8010.
Default empty → cohost (existing CoreFacade path). process_split_authorized stays false.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

import httpx
from fastapi import Request, Response
from fastapi.responses import JSONResponse


def eval_service_base_url() -> str:
    return (os.getenv("AIPLAT_EVAL_SERVICE_URL") or "").strip().rstrip("/")


def eval_proxy_enabled() -> bool:
    return bool(eval_service_base_url())


async def proxy_eval_store(
    request: Request,
    *,
    path: str,
    method: Optional[str] = None,
) -> Optional[Response]:
    """Forward to standalone if AIPLAT_EVAL_SERVICE_URL set; else return None (cohost).

    path is relative to /api/platform/apps/eval (e.g. /store/sets).
    """
    base = eval_service_base_url()
    if not base:
        return None

    verb = (method or request.method or "GET").upper()
    rel = path if path.startswith("/") else f"/{path}"
    url = f"{base}/api/platform/apps/eval{rel}"

    headers: Dict[str, str] = {}
    auth = request.headers.get("authorization")
    if auth:
        headers["authorization"] = auth
    ctype = request.headers.get("content-type")
    if ctype:
        headers["content-type"] = ctype

    body = await request.body() if verb in {"POST", "PUT", "PATCH"} else None
    params = list(request.query_params.multi_items())

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            upstream = await client.request(
                verb, url, headers=headers, content=body, params=params
            )
    except httpx.HTTPError as exc:
        return JSONResponse(
            status_code=502,
            content={
                "data": {
                    "ok": False,
                    "error": "eval_upstream_unreachable",
                    "detail": str(exc),
                    "upstream": url,
                    "process_split_authorized": False,
                }
            },
        )

    # Pass through JSON when possible; otherwise raw body.
    try:
        payload: Any = upstream.json()
        return JSONResponse(status_code=upstream.status_code, content=payload)
    except ValueError:
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "application/octet-stream"),
        )


def proxy_status() -> Dict[str, Any]:
    """Same-file wiring + diagnostics for dual-mode."""
    base = eval_service_base_url()
    enabled = bool(base)
    _ = eval_proxy_enabled()
    return {
        "enabled": enabled,
        "upstream": base or None,
        "mode": "proxy" if enabled else "cohost",
        "process_split_authorized": False,
    }


def _probe_paths() -> Tuple[str, ...]:
    """Documented proxied suffixes (for tests / status)."""
    return (
        "/store/healthz",
        "/store/sets",
        "/store/reports",
    )
