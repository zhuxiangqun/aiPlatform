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
    x_aiplat_actor_role: Optional[str] = Header(None, alias="X-AIPLAT-ACTOR-ROLE"),
):
    """ObjectSet 只读查询（租户前置 + L1 + ABox role ACL）。

    Args:
        request: FastAPI Request。
        body: E.1 请求。
        tenant_id: 租户。
        x_aiplat_scopes: 权限 scopes。
        x_aiplat_actor_role: 角色（透传字段/实例 ACL）。
    """
    from core.api.core_facade import query_object_set

    permissions = _parse_scopes(x_aiplat_scopes)
    if not permissions:
        permissions = _parse_scopes(request.headers.get("X-AIPLAT-SCOPES"))
    role = (x_aiplat_actor_role or request.headers.get("X-AIPLAT-ACTOR-ROLE") or "").strip()

    out = await query_object_set(
        body.model_dump(),
        tenant_id=tenant_id,
        permissions=permissions or None,
        role=role,
    )
    status = out.get("status")
    if status == "not_found":
        raise HTTPException(status_code=404, detail=out.get("reason") or "not_found")
    if status == "policy_denied":
        raise HTTPException(status_code=403, detail=out.get("reason") or "policy_denied")
    if status == "error":
        raise HTTPException(status_code=400, detail=out.get("reason") or "error")
    return out


class WhereExprProductBody(BaseModel):
    """N07/N22 产品面 `$expr`/`$where` 探针。"""

    item: Dict[str, Any] = Field(default_factory=dict)
    filter: Dict[str, Any] = Field(default_factory=dict)
    max_depth: int = Field(4, ge=1, le=8)


class WhereExprProductGateBody(BaseModel):
    """产品面门槛门探针。"""

    suite: Optional[Dict[str, Any]] = None


@router.post("/object-sets/product/where-expr")
async def object_set_where_expr_product_route(
    body: WhereExprProductBody = Body(...),
) -> Dict[str, Any]:
    """N07/N22 产品面：有界 `$expr` / `$where` 结构化回执（非 certified）。

    Args:
        body: item + filter。
    """
    from core.api.core_facade import evaluate_object_set_where_expr_product

    return evaluate_object_set_where_expr_product(
        body.item,
        body.filter,
        max_depth=body.max_depth,
    )


@router.post("/object-sets/product/suite")
async def object_set_where_expr_product_suite_route() -> Dict[str, Any]:
    """N07/N22 产品面 where/expr 套件。"""
    from core.api.core_facade import run_object_set_where_expr_product_suite

    return run_object_set_where_expr_product_suite()


@router.post("/object-sets/product/gate")
async def object_set_where_expr_product_gate_route(
    body: WhereExprProductGateBody = Body(default_factory=WhereExprProductGateBody),
) -> Dict[str, Any]:
    """N07/N22 产品面 where/expr 门槛门。

    Args:
        body: 可选 suite 回执。
    """
    from core.api.core_facade import (
        evaluate_object_set_where_expr_product_gate,
        run_object_set_where_expr_product_suite,
    )

    suite = body.suite
    if suite is None:
        suite = run_object_set_where_expr_product_suite()
    return evaluate_object_set_where_expr_product_gate(suite)
