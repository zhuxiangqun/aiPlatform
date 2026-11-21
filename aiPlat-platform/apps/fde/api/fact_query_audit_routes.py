"""FDE N19 Fact/Query 统一审计 — 薄路由，经 CoreFacade。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-fact-query-audit"])


class SnapshotBody(BaseModel):
    """写入统一审计快照。"""

    kind: str = Field(..., min_length=1)
    subject_ref: str = Field(..., min_length=1)
    before_snapshot: Optional[Dict[str, Any]] = None
    after_snapshot: Optional[Dict[str, Any]] = None
    runtime_authority: str = Field("fact_ledger", min_length=1)
    meta: Optional[Dict[str, Any]] = None


class GateBody(BaseModel):
    """门槛门探针。"""

    suite: Optional[Dict[str, Any]] = None


@router.post("/fact-query-audit/snapshots")
async def record_fact_query_audit_route(
    body: SnapshotBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """写入 Fact/Query 统一审计快照。

    Args:
        body: 快照载荷。
        tenant_id: 租户。
    """
    from core.api.core_facade import record_fact_query_audit_snapshot

    try:
        return record_fact_query_audit_snapshot(
            tenant_id=tenant_id,
            kind=body.kind,
            subject_ref=body.subject_ref,
            before_snapshot=body.before_snapshot,
            after_snapshot=body.after_snapshot,
            runtime_authority=body.runtime_authority,
            meta=body.meta,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/fact-query-audit/snapshots")
async def list_fact_query_audit_route(
    tenant_id: str = Query(..., description="tenant id (required)"),
    kind: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """列出统一审计快照。

    Args:
        tenant_id: 租户。
        kind: 可选 fact/query。
        limit: 上限。
    """
    from core.api.core_facade import list_fact_query_audit_snapshots

    try:
        return list_fact_query_audit_snapshots(
            tenant_id=tenant_id,
            kind=kind,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/fact-query-audit/suite")
async def run_fact_query_audit_suite_route():
    """运行 Fact/Query 统一审计套件。"""
    from core.api.core_facade import run_fact_query_audit_suite

    return run_fact_query_audit_suite()


@router.post("/fact-query-audit/gate")
async def evaluate_fact_query_audit_gate_route(
    body: GateBody = Body(default_factory=GateBody),
):
    """Fact/Query 统一审计门槛门。

    Args:
        body: 可选 suite 回执。
    """
    from core.api.core_facade import (
        evaluate_fact_query_audit_gate,
        run_fact_query_audit_suite,
    )

    suite = body.suite
    if suite is None:
        suite = run_fact_query_audit_suite()
    return evaluate_fact_query_audit_gate(suite)
