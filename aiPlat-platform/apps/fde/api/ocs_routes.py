"""FDE OCS — 薄路由，经 CoreFacade（v4.3.1 §13.4）。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["fde-ocs"])


@router.get("/ocs/{domain_id}")
async def get_domain_ocs_route(
    domain_id: str,
    credit_test_evidence: bool = Query(
        False, description="include C6 test-evidence credit"
    ),
):
    """读取域 OCS 分解。

    Args:
        domain_id: 域 id。
        credit_test_evidence: 是否计入 C6 测试加分。
    """
    from core.api.core_facade import compute_domain_ocs

    out = compute_domain_ocs(
        domain_id, credit_test_evidence=credit_test_evidence
    )
    if out.get("error"):
        raise HTTPException(status_code=404, detail=out.get("error"))
    return out


@router.get("/ocs/{domain_id}/gate")
async def evaluate_ocs_gate_route(
    domain_id: str,
    threshold: Optional[float] = Query(None, ge=0, le=100),
    credit_test_evidence: bool = Query(False),
):
    """OCS 门槛门。

    Args:
        domain_id: 域 id。
        threshold: 可选门槛（不得低于域配置/默认 80）。
        credit_test_evidence: 是否计入 C6 测试加分。
    """
    from core.api.core_facade import evaluate_ocs_gate

    return evaluate_ocs_gate(
        domain_id,
        threshold=threshold,
        credit_test_evidence=credit_test_evidence,
    )
