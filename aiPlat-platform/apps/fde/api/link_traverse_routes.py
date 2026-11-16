"""FDE link.traverse — 薄路由，经 CoreFacade（只读）。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-link-traverse"])


class LinkTraverseBody(BaseModel):
    """附录 F.2 link.traverse 请求体（HTTP）。"""

    start_id: str = Field(..., min_length=1)
    object_type: str = ""
    link_types: List[str] = Field(default_factory=list)
    max_hops: int = Field(2, ge=1, le=5)
    domain_id: str = ""
    direction: str = "both"


def _parse_scopes(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]


@router.post("/links/traverse")
async def traverse_links_route(
    request: Request,
    body: LinkTraverseBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
    x_aiplat_scopes: Optional[str] = Header(None, alias="X-AIPLAT-SCOPES"),
):
    """多跳链接遍历（租户前置 + L1 permissions）。

    Args:
        request: FastAPI Request。
        body: traverse 请求。
        tenant_id: 租户。
        x_aiplat_scopes: 权限 scopes。
    """
    from core.api.core_facade import traverse_object_links

    permissions = _parse_scopes(x_aiplat_scopes)
    if not permissions:
        permissions = _parse_scopes(request.headers.get("X-AIPLAT-SCOPES"))

    out = await traverse_object_links(
        body.model_dump(),
        tenant_id=tenant_id,
        permissions=permissions or None,
    )
    status = out.get("status")
    if status == "policy_denied":
        raise HTTPException(status_code=403, detail=out.get("reason") or "policy_denied")
    if status == "error":
        raise HTTPException(status_code=400, detail=out.get("reason") or "error")
    return out
