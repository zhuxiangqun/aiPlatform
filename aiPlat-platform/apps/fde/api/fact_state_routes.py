"""FDE N12 Fact 状态机 — 薄路由，经 CoreFacade。"""
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-fact-state"])


class FactTransitionBody(BaseModel):
    """Fact 审核/生命周期转换。"""

    to_status: str = Field(..., min_length=1)
    actor: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    role: str = Field(
        "",
        description="caller role for N04/N12 reviewer RBAC (required on publish)",
    )


class ValidateSequenceBody(BaseModel):
    """状态序列合法性探针。"""

    machine: str = Field(..., min_length=1)
    steps: List[str] = Field(..., min_length=2)


class ClaimTransitionBody(BaseModel):
    """Claim 状态写转换（读当前态 → 合法边 → 审计 → put_claim）。"""

    to_status: str = Field(..., min_length=1)
    actor: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)


class FactStateGateBody(BaseModel):
    """门槛门探针。"""

    checks: Dict[str, bool] = Field(default_factory=dict)


@router.get("/fact-state/machines")
async def dump_fact_state_machines_route():
    """导出三机边表。"""
    from core.api.core_facade import dump_fact_state_machines

    return dump_fact_state_machines()


@router.get("/fact-state/transitions")
async def list_fact_state_transitions_route(
    tenant_id: str = Query(..., description="tenant id (required)"),
    record_id: Optional[str] = Query(None),
    machine: Optional[str] = Query(None),
):
    """列出转换审计。

    Args:
        tenant_id: 租户。
        record_id: 可选记录。
        machine: 可选状态机。
    """
    from core.api.core_facade import list_fact_state_transitions

    return {
        "transitions": list_fact_state_transitions(
            tenant_id=tenant_id,
            record_id=record_id,
            machine=machine,
        )
    }


@router.post("/fact-state/validate-sequence")
async def validate_fact_state_sequence_route(
    body: ValidateSequenceBody = Body(...),
):
    """校验状态序列逐步合法（诊断用）。

    Args:
        body: 状态机名与有序状态列表。
    """
    from core.api.core_facade import validate_fact_state_sequence

    return validate_fact_state_sequence(machine=body.machine, steps=body.steps)


@router.post("/facts/{fact_id}/review-transition")
async def transition_fact_review_route(
    fact_id: str,
    body: FactTransitionBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """审核态转换（publish 须 body.role）。

    Args:
        fact_id: Fact ID。
        body: 目标态、人因与角色。
        tenant_id: 租户。
    """
    from core.api.core_facade import transition_fact_review

    try:
        return await transition_fact_review(
            fact_id=fact_id,
            tenant_id=tenant_id,
            to_status=body.to_status,
            actor=body.actor,
            reason=body.reason,
            role=body.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/facts/{fact_id}/lifecycle-transition")
async def transition_fact_lifecycle_route(
    fact_id: str,
    body: FactTransitionBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """生命周期转换。

    Args:
        fact_id: Fact ID。
        body: 目标态与人因。
        tenant_id: 租户。
    """
    from core.api.core_facade import transition_fact_lifecycle

    try:
        return await transition_fact_lifecycle(
            fact_id=fact_id,
            tenant_id=tenant_id,
            to_status=body.to_status,
            actor=body.actor,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/claims/{claim_id}/status-transition")
async def transition_claim_status_route(
    claim_id: str,
    body: ClaimTransitionBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """Claim 状态写转换（N03 deepen；非全量认证）。

    Args:
        claim_id: Claim ID。
        body: 目标态与人因。
        tenant_id: 租户。
    """
    from core.api.core_facade import transition_claim_status

    try:
        return await transition_claim_status(
            claim_id=claim_id,
            tenant_id=tenant_id,
            to_status=body.to_status,
            actor=body.actor,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/fact-state/gate")
async def evaluate_fact_state_gate_route(
    body: FactStateGateBody = Body(default_factory=FactStateGateBody),
):
    """评估 N12 门槛门（非全量认证）。

    Args:
        body: 探针 checks。
    """
    from core.api.core_facade import evaluate_fact_state_gate

    return evaluate_fact_state_gate(checks=body.checks or None)
