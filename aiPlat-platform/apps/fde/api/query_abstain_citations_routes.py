"""FDE N21 查询 abstain+citations — 薄路由，经 CoreFacade。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-query-abstain-citations"])


class ValidateBody(BaseModel):
    """校验查询响应。"""

    response: Dict[str, Any] = Field(default_factory=dict)
    require_citations_on_hit: bool = True


class EnforceBody(BaseModel):
    """归一化查询响应。"""

    response: Dict[str, Any] = Field(default_factory=dict)
    require_citations_on_hit: bool = True


class GateBody(BaseModel):
    """门槛门探针。"""

    suite: Optional[Dict[str, Any]] = None


@router.post("/query-abstain-citations/validate")
async def validate_query_abstain_citations_route(
    body: ValidateBody = Body(...),
):
    """校验 abstain+citations 防假绿规则。

    Args:
        body: 响应载荷。
    """
    from core.api.core_facade import validate_query_abstain_citations

    try:
        return validate_query_abstain_citations(
            response=body.response,
            require_citations_on_hit=body.require_citations_on_hit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/query-abstain-citations/enforce")
async def enforce_query_abstain_citations_route(
    body: EnforceBody = Body(...),
):
    """归一化查询响应。

    Args:
        body: 响应载荷。
    """
    from core.api.core_facade import enforce_query_abstain_citations

    try:
        return enforce_query_abstain_citations(
            response=body.response,
            require_citations_on_hit=body.require_citations_on_hit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/query-abstain-citations/suite")
async def run_query_abstain_citations_suite_route():
    """运行 abstain+citations 套件。"""
    from core.api.core_facade import run_query_abstain_citations_suite

    return await run_query_abstain_citations_suite()


@router.post("/query-abstain-citations/gate")
async def evaluate_query_abstain_citations_gate_route(
    body: GateBody = Body(default_factory=GateBody),
):
    """abstain+citations 门槛门。

    Args:
        body: 可选 suite 回执。
    """
    from core.api.core_facade import (
        evaluate_query_abstain_citations_gate,
        run_query_abstain_citations_suite,
    )

    suite = body.suite
    if suite is None:
        suite = await run_query_abstain_citations_suite()
    return evaluate_query_abstain_citations_gate(suite)
