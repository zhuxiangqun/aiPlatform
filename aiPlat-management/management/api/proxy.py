import os
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request, Response


def _base_url(env_name: str, default: str) -> str:
    return os.getenv(env_name, default).rstrip("/")


async def _proxy(request: Request, upstream_base: str, upstream_path: str) -> Response:
    method = request.method.upper()
    params = dict(request.query_params)
    body = await request.body()

    # Forward most headers; strip hop-by-hop.
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)

    url = f"{upstream_base}{upstream_path}"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.request(method, url, params=params, content=body, headers=headers)
        return Response(content=r.content, status_code=r.status_code, media_type=r.headers.get("content-type"))
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Upstream unavailable: {str(e)}")


def build_platform_proxy_router() -> APIRouter:
    router = APIRouter(prefix="/platform", tags=["platform"])
    upstream = _base_url("AIPLAT_PLATFORM_ENDPOINT", "http://localhost:8003")

    @router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def platform_proxy(path: str, request: Request):
        return await _proxy(request, upstream, f"/{path}")

    return router


def build_app_proxy_router() -> APIRouter:
    router = APIRouter(prefix="/app", tags=["app"])
    upstream = _base_url("AIPLAT_APP_ENDPOINT", "http://localhost:8004")

    @router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def app_proxy(path: str, request: Request):
        return await _proxy(request, upstream, f"/{path}")

    return router

