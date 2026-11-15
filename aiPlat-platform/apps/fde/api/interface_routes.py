"""FDE Interface 兼容性校验 — 薄路由，经 CoreFacade 调 InterfaceRegistry。"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-interfaces"])


class InterfaceCompatBody(BaseModel):
    """兼容性校验请求体。"""

    object_type_id: str = Field(..., min_length=1, max_length=120)


def _parse_scopes(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]


@router.post("/interfaces/{interface_id}/check-compatibility")
async def check_interface_compatibility_route(
    request: Request,
    interface_id: str,
    body: InterfaceCompatBody,
    x_aiplat_scopes: Optional[str] = Header(None, alias="X-AIPLAT-SCOPES"),
):
    """校验 ObjectType 是否兼容 Interface（L1 permissions + 形状覆盖）。

    Args:
        request: FastAPI Request。
        interface_id: InterfaceContract id（路径可含冒号，需 URL 编码）。
        body: 含 object_type_id。
        x_aiplat_scopes: 权限 scopes。
    """
    from core.api.core_facade import check_interface_compatibility

    permissions = _parse_scopes(x_aiplat_scopes)
    if not permissions:
        permissions = _parse_scopes(request.headers.get("X-AIPLAT-SCOPES"))

    out = check_interface_compatibility(
        interface_id,
        body.object_type_id,
        permissions=permissions or None,
    )
    status = out.get("status")
    if status == "not_found":
        raise HTTPException(status_code=404, detail=out.get("reason") or "not_found")
    if status == "policy_denied":
        raise HTTPException(status_code=403, detail=out.get("reason") or "policy_denied")
    if status == "object_type_not_found":
        raise HTTPException(
            status_code=404, detail=out.get("reason") or "object_type_not_found"
        )
    # not_an_implementer / incompatible 仍 200，body 带 compatible=false
    return out
