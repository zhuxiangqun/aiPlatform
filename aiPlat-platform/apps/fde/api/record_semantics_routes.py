"""FDE N17 记录级语义校验 — 薄路由，经 CoreFacade。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-record-semantics"])


class ValidateRecordBody(BaseModel):
    """单条记录语义校验。"""

    kind: str = Field(..., min_length=1)
    data: Dict[str, Any] = Field(default_factory=dict)


class ValidateTransitionBody(BaseModel):
    """状态机单步转换校验。"""

    machine: str = Field(..., min_length=1)
    from_state: str = Field(..., min_length=1)
    to_state: str = Field(..., min_length=1)


class ScanBody(BaseModel):
    """FactLedger 扫描。"""

    domain_id: Optional[str] = None
    collection_id: Optional[str] = None
    limit: int = Field(100, ge=1, le=500)


class GateBody(BaseModel):
    """门槛门探针。"""

    suite: Optional[Dict[str, Any]] = None


@router.post("/record-semantics/validate")
async def validate_record_semantics_route(
    body: ValidateRecordBody = Body(...),
):
    """校验单条记录语义。

    Args:
        body: kind + data。
    """
    from core.api.core_facade import validate_record_semantics

    try:
        return validate_record_semantics(kind=body.kind, data=body.data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/record-semantics/transition")
async def validate_record_transition_route(
    body: ValidateTransitionBody = Body(...),
):
    """校验状态机单步转换。

    Args:
        body: machine/from/to。
    """
    from core.api.core_facade import validate_record_transition

    try:
        return validate_record_transition(
            machine=body.machine,
            from_state=body.from_state,
            to_state=body.to_state,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/record-semantics/scan")
async def scan_record_semantics_route(
    body: ScanBody = Body(default_factory=ScanBody),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """扫描 FactLedger 记录级语义违规。

    Args:
        body: 可选域/集合过滤。
        tenant_id: 租户。
    """
    from core.api.core_facade import scan_record_semantics_facts

    try:
        return await scan_record_semantics_facts(
            tenant_id=tenant_id,
            domain_id=body.domain_id,
            collection_id=body.collection_id,
            limit=body.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/record-semantics/suite")
async def run_record_semantics_suite_route():
    """运行记录级语义套件。"""
    from core.api.core_facade import run_record_semantics_suite

    return await run_record_semantics_suite()


@router.post("/record-semantics/gate")
async def evaluate_record_semantics_gate_route(
    body: GateBody = Body(default_factory=GateBody),
):
    """记录级语义门槛门。

    Args:
        body: 可选 suite 回执。
    """
    from core.api.core_facade import (
        evaluate_record_semantics_gate,
        run_record_semantics_suite,
    )

    suite = body.suite
    if suite is None:
        suite = await run_record_semantics_suite()
    return evaluate_record_semantics_gate(suite)
