"""FDE N04 来源策略与冲突裁决 — 薄路由，经 CoreFacade。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-source-policy"])


class SourcePolicyBody(BaseModel):
    """登记来源策略。"""

    policy_id: str = Field(..., min_length=1)
    authority: str = Field(..., min_length=1)
    freshness: Dict[str, Any] = Field(...)
    scope: List[str] = Field(..., min_length=1)
    license: str = Field(..., min_length=1)
    trust: str = Field(..., min_length=1)
    conflict_rule: str = Field(..., min_length=1)
    source_id: str = ""


class AdjudicateBody(BaseModel):
    """人审裁决。"""

    actor: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    accepted_fact_id: str = Field(..., min_length=1)


class ScanConflictsBody(BaseModel):
    """扫描冲突。"""

    collection_id: str = Field(..., min_length=1)
    subject: str = ""
    predicate: str = ""


class SourcePolicyGateBody(BaseModel):
    """门槛门探针结果。"""

    checks: Dict[str, bool] = Field(default_factory=dict)


@router.post("/source-policies")
async def register_source_policy_route(
    body: SourcePolicyBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """登记来源策略。

    Args:
        body: 策略字段。
        tenant_id: 租户。
    """
    from core.api.core_facade import register_source_policy

    try:
        return register_source_policy(
            tenant_id=tenant_id,
            policy_id=body.policy_id,
            authority=body.authority,
            freshness=body.freshness,
            scope=body.scope,
            license=body.license,
            trust=body.trust,
            conflict_rule=body.conflict_rule,
            source_id=body.source_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/source-policies/{policy_id}")
async def get_source_policy_route(
    policy_id: str,
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """读取来源策略。

    Args:
        policy_id: 策略 ID。
        tenant_id: 租户。
    """
    from core.api.core_facade import get_source_policy

    out = get_source_policy(policy_id, tenant_id=tenant_id)
    if out is None:
        raise HTTPException(status_code=404, detail="source_policy not found")
    return out


@router.get("/conflicts")
async def list_open_conflicts_route(
    tenant_id: str = Query(..., description="tenant id (required)"),
    subject: Optional[str] = Query(None),
    predicate: Optional[str] = Query(None),
):
    """列出未裁决冲突。

    Args:
        tenant_id: 租户。
        subject: 可选主语。
        predicate: 可选谓词。
    """
    from core.api.core_facade import list_open_conflicts

    return {
        "conflicts": list_open_conflicts(
            tenant_id=tenant_id,
            subject=subject,
            predicate=predicate,
        )
    }


@router.post("/conflicts/scan")
async def scan_conflicts_route(
    body: ScanConflictsBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """扫描 FactLedger 并落库冲突。

    Args:
        body: 集合与可选键。
        tenant_id: 租户。
    """
    from core.api.core_facade import scan_and_record_conflicts

    conflicts = await scan_and_record_conflicts(
        tenant_id=tenant_id,
        collection_id=body.collection_id,
        subject=body.subject or None,
        predicate=body.predicate or None,
    )
    return {"conflicts": conflicts}


@router.post("/conflicts/{conflict_id}/adjudicate")
async def adjudicate_conflict_route(
    conflict_id: str,
    body: AdjudicateBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """人审裁决冲突。

    Args:
        conflict_id: 冲突 ID。
        body: 裁决人/理由/采纳 Fact。
        tenant_id: 租户。
    """
    from core.api.core_facade import adjudicate_conflict

    try:
        return adjudicate_conflict(
            conflict_id=conflict_id,
            tenant_id=tenant_id,
            actor=body.actor,
            reason=body.reason,
            accepted_fact_id=body.accepted_fact_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/source-policies/gate")
async def evaluate_source_policy_gate_route(
    body: SourcePolicyGateBody = Body(default_factory=SourcePolicyGateBody),
):
    """评估 N04 门槛门（非全量认证）。

    Args:
        body: 探针 checks。
    """
    from core.api.core_facade import evaluate_source_policy_gate

    return evaluate_source_policy_gate(checks=body.checks or None)
