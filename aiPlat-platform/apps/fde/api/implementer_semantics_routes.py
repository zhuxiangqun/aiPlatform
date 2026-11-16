"""FDE N18 实现方语义测试 — 薄路由，经 CoreFacade。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

router = APIRouter(tags=["fde-implementer-semantics"])


@router.post("/implementer-semantics/run")
async def run_implementer_semantics_route(
    work_dir: Optional[str] = Query(None, description="optional suite work dir"),
):
    """跑 N18 最小实现方语义套件。

    Args:
        work_dir: 可选工作目录。
    """
    from core.api.core_facade import run_implementer_semantics_suite

    return await run_implementer_semantics_suite(work_dir=work_dir)


@router.post("/implementer-semantics/gate")
async def evaluate_implementer_semantics_gate_route(
    work_dir: Optional[str] = Query(None, description="optional suite work dir"),
):
    """先跑套件再评估门槛门（非 N18 全量认证）。

    Args:
        work_dir: 可选工作目录。
    """
    from core.api.core_facade import (
        evaluate_implementer_semantics_gate,
        run_implementer_semantics_suite,
    )

    suite = await run_implementer_semantics_suite(work_dir=work_dir)
    gate = evaluate_implementer_semantics_gate(suite)
    return {"suite": suite, "gate": gate}
