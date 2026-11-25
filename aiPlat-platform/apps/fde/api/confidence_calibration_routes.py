"""FDE Confidence Calibration — 薄路由，经 CoreFacade（附录 O）。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-confidence-calibration"])


class CalibrationPublishBody(BaseModel):
    """发布校准报告。"""

    domain: str = Field(..., min_length=1)
    query_type: str = Field(..., min_length=1)
    dataset_version: str = Field(..., min_length=1)
    sample_size: int = Field(..., ge=0)
    label_protocol: str = Field(..., min_length=1)
    inter_annotator_agreement: float = Field(..., ge=0.0, le=1.0)
    weights: Dict[str, Any] = Field(default_factory=dict)
    calibration_version: str = Field(..., min_length=1)
    ece: float
    brier: float
    high_precision: float = Field(..., ge=0.0, le=1.0)
    coverage: float = Field(..., ge=0.0, le=1.0)
    approved_by: str = Field(..., min_length=1)
    valid_until: str = Field(..., min_length=1)
    model_version: str = ""
    index_version: str = ""
    source_policy_version: str = ""
    sample_shortage_justification: str = ""


class ConfidenceResolveBody(BaseModel):
    """解析 confidence 上限。"""

    domain: str = Field(..., min_length=1)
    query_type: str = Field(..., min_length=1)
    requested: str = "high"


class EceTrainBody(BaseModel):
    """N13 residual：样本 ECE/Brier 有界训练（非准确率宣称）。"""

    samples: List[Dict[str, Any]] = Field(default_factory=list)
    n_bins: int = Field(10, ge=1, le=50)
    high_threshold: float = Field(0.8, ge=0.0, le=1.0)


@router.post("/confidence-calibrations")
async def publish_confidence_calibration_route(
    body: CalibrationPublishBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """发布 Confidence Calibration Report。

    Args:
        body: 报告字段。
        tenant_id: 租户。
    """
    from core.api.core_facade import publish_confidence_calibration

    out = publish_confidence_calibration(
        tenant_id=tenant_id,
        domain=body.domain,
        query_type=body.query_type,
        dataset_version=body.dataset_version,
        sample_size=body.sample_size,
        label_protocol=body.label_protocol,
        inter_annotator_agreement=body.inter_annotator_agreement,
        weights=body.weights,
        calibration_version=body.calibration_version,
        ece=body.ece,
        brier=body.brier,
        high_precision=body.high_precision,
        coverage=body.coverage,
        approved_by=body.approved_by,
        valid_until=body.valid_until,
        model_version=body.model_version,
        index_version=body.index_version,
        source_policy_version=body.source_policy_version,
        sample_shortage_justification=body.sample_shortage_justification,
    )
    if out.get("status") == "invalid":
        raise HTTPException(status_code=400, detail=out.get("error") or "invalid")
    return out


@router.get("/confidence-calibrations/{calibration_id}")
async def get_confidence_calibration_route(
    calibration_id: str,
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """按 id 读取校准报告。

    Args:
        calibration_id: 报告 id。
        tenant_id: 租户。
    """
    from core.api.core_facade import get_confidence_calibration

    out = get_confidence_calibration(calibration_id, tenant_id=tenant_id)
    if not out:
        raise HTTPException(status_code=404, detail="calibration_not_found")
    return out


@router.get("/confidence-calibrations")
async def get_active_confidence_calibration_route(
    tenant_id: str = Query(..., description="tenant id (required)"),
    domain: str = Query(..., min_length=1),
    query_type: str = Query(..., min_length=1),
):
    """读取域/query_type 的 active 校准报告。

    Args:
        tenant_id: 租户。
        domain: 域。
        query_type: 查询类型。
    """
    from core.api.core_facade import get_confidence_calibration

    out = get_confidence_calibration(
        tenant_id=tenant_id, domain=domain, query_type=query_type
    )
    if not out:
        raise HTTPException(status_code=404, detail="calibration_not_found")
    return out


@router.post("/confidence-calibrations/validate")
async def validate_confidence_calibration_route(
    tenant_id: str = Query(..., description="tenant id (required)"),
    domain: str = Query(..., min_length=1),
    query_type: str = Query(..., min_length=1),
    calibration_id: Optional[str] = Query(None),
):
    """校验校准报告门槛。

    Args:
        tenant_id: 租户。
        domain: 域。
        query_type: 查询类型。
        calibration_id: 可选报告 id。
    """
    from core.api.core_facade import validate_confidence_calibration

    return validate_confidence_calibration(
        calibration_id,
        tenant_id=tenant_id,
        domain=domain,
        query_type=query_type,
    )


@router.post("/confidence-calibrations/resolve")
async def resolve_confidence_ceiling_route(
    body: ConfidenceResolveBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """解析允许的最大 confidence。

    Args:
        body: 域/类型/请求档位。
        tenant_id: 租户。
    """
    from core.api.core_facade import resolve_confidence_ceiling

    out = resolve_confidence_ceiling(
        tenant_id=tenant_id,
        domain=body.domain,
        query_type=body.query_type,
        requested=body.requested,
    )
    if out.get("status") == "invalid":
        raise HTTPException(status_code=400, detail=out.get("error") or "invalid")
    return out


@router.post("/confidence-calibrations/ece-train")
async def compute_ece_from_samples_route(
    body: EceTrainBody = Body(...),
):
    """N13 residual：从标注样本计算 ECE/Brier（非 certified）。

    Args:
        body: samples / n_bins / high_threshold。
    """
    from core.api.core_facade import compute_ece_from_samples

    return compute_ece_from_samples(
        body.samples,
        n_bins=body.n_bins,
        high_threshold=body.high_threshold,
    )


@router.post("/confidence-calibrations/product/ece-train")
async def compute_ece_from_samples_product_route(
    body: EceTrainBody = Body(...),
):
    """N13 产品面：有界样本 ECE/Brier（默认可用；非 certified）。

    Args:
        body: samples / n_bins / high_threshold。
    """
    from core.api.core_facade import compute_ece_from_samples_product

    return compute_ece_from_samples_product(
        body.samples,
        n_bins=body.n_bins,
        high_threshold=body.high_threshold,
    )


@router.post("/confidence-calibrations/product/suite")
async def ece_train_product_suite_route() -> Dict[str, Any]:
    """N13 产品面套件。"""
    from core.api.core_facade import run_ece_train_product_suite

    return run_ece_train_product_suite()


@router.post("/confidence-calibrations/product/gate")
async def ece_train_product_gate_route(
    body: Optional[Dict[str, Any]] = Body(default=None),
) -> Dict[str, Any]:
    """N13 产品面门槛门。

    Args:
        body: 可选已跑 suite；缺省时现场跑套件。
    """
    from core.api.core_facade import (
        evaluate_ece_train_product_gate,
        run_ece_train_product_suite,
    )

    suite = body if isinstance(body, dict) and body.get("cases") else None
    if suite is None:
        suite = run_ece_train_product_suite()
    return evaluate_ece_train_product_gate(suite)
