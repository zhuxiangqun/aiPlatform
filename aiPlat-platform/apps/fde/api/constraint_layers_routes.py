"""FDE N20 约束分层 — 薄路由，经 CoreFacade。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-constraint-layers"])


class StackBody(BaseModel):
    """约束栈评估。"""

    risk_level: str = Field("medium")
    required_permissions: Optional[List[str]] = None
    actor_permissions: Optional[List[str]] = None
    soft_constraints: Optional[List[Dict[str, Any]]] = None
    require_audit: bool = True
    l1_present: bool = True


class GateBody(BaseModel):
    """门槛门探针。"""

    suite: Optional[Dict[str, Any]] = None


@router.post("/constraint-layers/evaluate")
async def evaluate_constraint_stack_route(
    body: StackBody = Body(...),
):
    """评估知识面 L1/L2/L3 约束栈。

    Args:
        body: 栈参数。
    """
    from core.api.core_facade import evaluate_knowledge_constraint_stack

    try:
        return evaluate_knowledge_constraint_stack(
            risk_level=body.risk_level,
            required_permissions=body.required_permissions,
            actor_permissions=body.actor_permissions,
            soft_constraints=body.soft_constraints,
            require_audit=body.require_audit,
            l1_present=body.l1_present,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/constraint-layers/suite")
async def run_constraint_layers_suite_route():
    """运行约束分层套件。"""
    from core.api.core_facade import run_constraint_layers_suite

    return run_constraint_layers_suite()


@router.post("/constraint-layers/gate")
async def evaluate_constraint_layers_gate_route(
    body: GateBody = Body(default_factory=GateBody),
):
    """约束分层门槛门。

    Args:
        body: 可选 suite 回执。
    """
    from core.api.core_facade import (
        evaluate_constraint_layers_gate,
        run_constraint_layers_suite,
    )

    suite = body.suite
    if suite is None:
        suite = run_constraint_layers_suite()
    return evaluate_constraint_layers_gate(suite)
