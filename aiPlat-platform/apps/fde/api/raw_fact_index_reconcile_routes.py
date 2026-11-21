"""FDE N14 Raw↔Fact↔Index 对账 — 薄路由，经 CoreFacade。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-raw-fact-index-reconcile"])


class ReconcileBody(BaseModel):
    """全链路对账。"""

    domain_id: Optional[str] = None
    collection_id: Optional[str] = None
    index_fact_ids: Optional[List[str]] = None
    extra_raw_ids: Optional[List[str]] = None
    limit: int = Field(500, ge=1, le=5000)


class GateBody(BaseModel):
    """门槛门探针。"""

    suite: Optional[Dict[str, Any]] = None


@router.post("/raw-fact-index-reconcile/run")
async def reconcile_raw_fact_index_route(
    body: ReconcileBody = Body(default_factory=ReconcileBody),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """运行 Raw↔Fact↔Index 对账。

    Args:
        body: 对账参数。
        tenant_id: 租户。
    """
    from core.api.core_facade import reconcile_raw_fact_index_chain

    try:
        return await reconcile_raw_fact_index_chain(
            tenant_id=tenant_id,
            domain_id=body.domain_id,
            collection_id=body.collection_id,
            index_fact_ids=body.index_fact_ids,
            extra_raw_ids=body.extra_raw_ids,
            limit=body.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/raw-fact-index-reconcile/suite")
async def run_raw_fact_index_reconcile_suite_route():
    """运行 Raw↔Fact↔Index 对账套件。"""
    from core.api.core_facade import run_raw_fact_index_reconcile_suite

    return await run_raw_fact_index_reconcile_suite()


@router.post("/raw-fact-index-reconcile/gate")
async def evaluate_raw_fact_index_reconcile_gate_route(
    body: GateBody = Body(default_factory=GateBody),
):
    """Raw↔Fact↔Index 对账门槛门。

    Args:
        body: 可选 suite 回执。
    """
    from core.api.core_facade import (
        evaluate_raw_fact_index_reconcile_gate,
        run_raw_fact_index_reconcile_suite,
    )

    suite = body.suite
    if suite is None:
        suite = await run_raw_fact_index_reconcile_suite()
    return evaluate_raw_fact_index_reconcile_gate(suite)
