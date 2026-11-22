"""FDE N08 Lv4 误报门 — 薄路由，经 CoreFacade。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-lv4-false-positive"])


class EvalBody(BaseModel):
    """Lv4 误报门评估。"""

    action_id: str = Field(..., min_length=1)
    total: int = Field(..., ge=0)
    false_positives: int = Field(..., ge=0)
    rollback_action_id: Optional[str] = None
    fp_rate_max: float = Field(0.005, gt=0.0, le=1.0)
    min_samples: Optional[int] = Field(None, ge=1)


class GateBody(BaseModel):
    """门槛门探针。"""

    suite: Optional[Dict[str, Any]] = None


@router.post("/lv4-false-positive/evaluate")
async def evaluate_lv4_fp_gate_route(body: EvalBody = Body(...)):
    """评估 Lv4 误报门。

    Args:
        body: 样本与回滚配置。
    """
    from core.api.core_facade import evaluate_lv4_false_positive

    try:
        return evaluate_lv4_false_positive(
            action_id=body.action_id,
            total=body.total,
            false_positives=body.false_positives,
            rollback_action_id=body.rollback_action_id,
            fp_rate_max=body.fp_rate_max,
            min_samples=body.min_samples,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/lv4-false-positive/suite")
async def run_lv4_false_positive_suite_route():
    """运行 Lv4 误报门套件。"""
    from core.api.core_facade import run_lv4_false_positive_gate_suite

    return run_lv4_false_positive_gate_suite()


@router.post("/lv4-false-positive/gate")
async def evaluate_lv4_false_positive_gate_route(
    body: GateBody = Body(default_factory=GateBody),
):
    """Lv4 误报门门槛门。

    Args:
        body: 可选 suite 回执。
    """
    from core.api.core_facade import (
        evaluate_lv4_false_positive_gate,
        run_lv4_false_positive_gate_suite,
    )

    suite = body.suite
    if suite is None:
        suite = run_lv4_false_positive_gate_suite()
    return evaluate_lv4_false_positive_gate(suite)
