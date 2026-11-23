"""FDE N01 DataSource vendor 驱动矩阵 — 薄路由，经 CoreFacade。"""
from __future__ import annotations

from typing import Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(tags=["fde-datasource-vendor-matrix"])


class VendorMatrixGateBody(BaseModel):
    """门槛门探针（透传 suite）。"""

    suite: Optional[Dict] = None


@router.get("/datasource/vendor-matrix")
async def get_vendor_matrix_route():
    """返回 SQL vendor 驱动声明矩阵 + 软依赖探测（certified 恒 false）。"""
    from core.api.core_facade import get_datasource_vendor_driver_matrix

    return get_datasource_vendor_driver_matrix()


@router.get("/datasource/vendor-matrix/probe")
async def probe_vendor_route(
    vendor: str = Query(..., description="sqlite|postgresql|mysql|oracle"),
):
    """探测单个 vendor 驱动软依赖。

    Args:
        vendor: 声明轴上的 vendor 名。
    """
    from core.api.core_facade import probe_datasource_vendor_driver

    try:
        return probe_datasource_vendor_driver(vendor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/datasource/vendor-matrix/suite")
async def run_vendor_matrix_suite_route():
    """运行 vendor 驱动矩阵套件（certified 恒 false）。"""
    from core.api.core_facade import fact_ledger_run_datasource_vendor_matrix_suite

    return fact_ledger_run_datasource_vendor_matrix_suite()


@router.post("/datasource/vendor-matrix/gate")
async def evaluate_vendor_matrix_gate_route(
    body: VendorMatrixGateBody = Body(default_factory=VendorMatrixGateBody),
):
    """评估 vendor 驱动矩阵门槛门（certified 恒 false）。

    Args:
        body: 可选 suite 透传。
    """
    from core.api.core_facade import evaluate_fact_datasource_vendor_matrix_gate

    return evaluate_fact_datasource_vendor_matrix_gate(suite=body.suite)
