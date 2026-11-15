"""FDE ObjectSet 查询 — 薄路由，经 CoreFacade（只读）。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-object-sets"])


class ObjectSetQueryBody(BaseModel):
    """附录 E.1 请求体（HTTP）。"""

    object_type: str = Field(..., min_length=1)
    filter: Dict[str, Any] = Field(default_factory=dict)
    sort: List[Dict[str, str]] = Field(default_factory=list)
    limit: int = Field(50, ge=1, le=500)
    domain_id: str = ""
    aggregate: List[Dict[str, Any]] = Field(default_factory=list)


def _parse_scopes(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]


@router.post("/object-sets/query")
async def query_object_set_route(
    request: Request,
    body: ObjectSetQueryBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
    x_aiplat_scopes: Optional[str] = Header(None, alias="X-AIPLAT-SCOPES"),
):
    """ObjectSet 只读查询（租户前置 + L1 permissions）。

    Args:
        request: FastAPI Request。
        body: E.1 请求。
        tenant_id: 租户。
        x_aiplat_scopes: 权限 scopes。
    """
    from core.api.core_facade import query_object_set

    permissions = _parse_scopes(x_aiplat_scopes)
    if not permissions:
        permissions = _parse_scopes(request.headers.get("X-AIPLAT-SCOPES"))

    out = await query_object_set(
        body.model_dump(),
        tenant_id=tenant_id,
        permissions=permissions or None,
    )
    status = out.get("status")
    if status == "not_found":
        raise HTTPException(status_code=404, detail=out.get("reason") or "not_found")
    if status == "policy_denied":
        raise HTTPException(status_code=403, detail=out.get("reason") or "policy_denied")
    if status == "error":
        raise HTTPException(status_code=400, detail=out.get("reason") or "error")
    return out
