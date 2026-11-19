"""FDE Knowledge SDK — 薄路由，经 CoreFacade 生成表面/源码。"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request

router = APIRouter(tags=["fde-knowledge-sdk"])


def _parse_scopes(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]


@router.get("/sdk/surface/{object_type}")
async def sdk_surface_route(
    request: Request,
    object_type: str,
    x_aiplat_scopes: Optional[str] = Header(None, alias="X-AIPLAT-SCOPES"),
):
    """返回 ObjectType 的 SDK 表面（附录 E.3）。

    Args:
        request: FastAPI Request。
        object_type: ObjectType id。
        x_aiplat_scopes: 权限 scopes。
    """
    from core.api.core_facade import build_knowledge_sdk_surface

    permissions = _parse_scopes(x_aiplat_scopes)
    if not permissions:
        permissions = _parse_scopes(request.headers.get("X-AIPLAT-SCOPES"))

    out = build_knowledge_sdk_surface(
        object_type, permissions=permissions or None
    )
    status = out.get("status")
    if status == "not_found":
        raise HTTPException(status_code=404, detail=out.get("reason") or "not_found")
    if status == "policy_denied":
        raise HTTPException(status_code=403, detail=out.get("reason") or "policy_denied")
    if status == "error":
        raise HTTPException(status_code=400, detail=out.get("reason") or "error")
    return out


@router.post("/sdk/generate/{object_type}")
async def sdk_generate_route(
    request: Request,
    object_type: str,
    x_aiplat_scopes: Optional[str] = Header(None, alias="X-AIPLAT-SCOPES"),
):
    """生成仅经 CoreFacade 的 Python SDK 源码。

    Args:
        request: FastAPI Request。
        object_type: ObjectType id。
        x_aiplat_scopes: 权限 scopes。
    """
    from core.api.core_facade import generate_knowledge_sdk

    permissions = _parse_scopes(x_aiplat_scopes)
    if not permissions:
        permissions = _parse_scopes(request.headers.get("X-AIPLAT-SCOPES"))

    out = generate_knowledge_sdk(object_type, permissions=permissions or None)
    status = out.get("status")
    if status == "not_found":
        raise HTTPException(status_code=404, detail=out.get("reason") or "not_found")
    if status == "policy_denied":
        raise HTTPException(status_code=403, detail=out.get("reason") or "policy_denied")
    if status == "error":
        raise HTTPException(status_code=400, detail=out.get("reason") or "error")
    return out


@router.get("/sdk/object-types")
async def sdk_list_object_types_route(
    request: Request,
    x_aiplat_scopes: Optional[str] = Header(None, alias="X-AIPLAT-SCOPES"),
    tenant_id: Optional[str] = Query(None, description="unused; reserved"),
):
    """列出可生成 SDK 的 ObjectType。

    Args:
        request: FastAPI Request。
        x_aiplat_scopes: 权限 scopes。
        tenant_id: 预留。
    """
    from core.api.core_facade import list_knowledge_sdk_object_types

    permissions = _parse_scopes(x_aiplat_scopes)
    if not permissions:
        permissions = _parse_scopes(request.headers.get("X-AIPLAT-SCOPES"))

    out = list_knowledge_sdk_object_types(permissions=permissions or None)
    if out.get("status") == "policy_denied":
        raise HTTPException(status_code=403, detail=out.get("reason") or "policy_denied")
    return out


@router.post("/sdk/install/{object_type}")
async def sdk_install_route(
    request: Request,
    object_type: str,
    x_aiplat_scopes: Optional[str] = Header(None, alias="X-AIPLAT-SCOPES"),
):
    """写盘安装 Python Knowledge SDK 到 allowlist ``aiplat-sdk/aiplat/knowledge``。

    Args:
        request: FastAPI Request。
        object_type: ObjectType id。
        x_aiplat_scopes: 权限 scopes。
    """
    from core.api.core_facade import install_knowledge_sdk

    permissions = _parse_scopes(x_aiplat_scopes)
    if not permissions:
        permissions = _parse_scopes(request.headers.get("X-AIPLAT-SCOPES"))

    out = install_knowledge_sdk(object_type, permissions=permissions or None)
    status = out.get("status")
    if status == "not_found":
        raise HTTPException(status_code=404, detail=out.get("reason") or "not_found")
    if status == "policy_denied":
        raise HTTPException(status_code=403, detail=out.get("reason") or "policy_denied")
    if status == "error":
        raise HTTPException(status_code=400, detail=out.get("reason") or "error")
    return out
