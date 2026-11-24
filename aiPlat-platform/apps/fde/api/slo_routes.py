"""FDE Knowledge SLO 遥测 — 薄路由，经 CoreFacade（F1 deepen）。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request

router = APIRouter(tags=["fde-knowledge-slo"])


def _tenant_from(
    request: Request,
    x_tenant: Optional[str],
    body_tenant: str = "",
) -> str:
    """解析租户（body / header / identity）。

    Args:
        request: FastAPI Request。
        x_tenant: X-AIPLAT-TENANT-ID。
        body_tenant: body 内 tenant_id。
    """
    tid = str(body_tenant or "").strip()
    if tid:
        return tid
    if x_tenant:
        return str(x_tenant).strip()
    header = request.headers.get("X-AIPLAT-TENANT-ID") or ""
    if header:
        return str(header).strip()
    return ""


@router.get("/slo/snapshot")
async def slo_snapshot_route(
    request: Request,
    tenant_id: Optional[str] = Query(None),
    domain_id: Optional[str] = Query(None),
    window_hours: int = Query(24, ge=1, le=720),
    include_live: bool = Query(True),
    x_aiplat_tenant_id: Optional[str] = Header(None, alias="X-AIPLAT-TENANT-ID"),
) -> Dict[str, Any]:
    """返回知识系统 SLO 快照（目标 + 样本；非达标宣称）。

    Args:
        request: FastAPI Request。
        tenant_id: 租户 query。
        domain_id: 可选域。
        window_hours: 窗口小时。
        include_live: 是否合并 live 源。
        x_aiplat_tenant_id: 租户 header。
    """
    from core.api.core_facade import get_knowledge_slo_snapshot

    tid = _tenant_from(request, x_aiplat_tenant_id, tenant_id or "")
    if not tid:
        raise HTTPException(status_code=400, detail="tenant_id_required")
    out = get_knowledge_slo_snapshot(
        tid,
        domain_id=str(domain_id or ""),
        window_hours=int(window_hours),
        include_live=bool(include_live),
    )
    if out.get("status") == "error":
        raise HTTPException(status_code=400, detail=out.get("reason") or "error")
    return out


@router.post("/slo/evaluate-wiring")
async def slo_evaluate_wiring_route(
    request: Request,
    x_aiplat_tenant_id: Optional[str] = Header(None, alias="X-AIPLAT-TENANT-ID"),
) -> Dict[str, Any]:
    """评估 SLO 接线门（wiring_ok；attainment/certified 恒假）。

    Args:
        request: FastAPI Request（可选 JSON：tenant_id/domain_id/window_hours）。
        x_aiplat_tenant_id: 租户 header。
    """
    from core.api.core_facade import evaluate_knowledge_slo_wiring_gate

    body: Dict[str, Any] = {}
    try:
        raw = await request.json()
        if isinstance(raw, dict):
            body = raw
    except Exception:
        body = {}

    tid = _tenant_from(
        request, x_aiplat_tenant_id, str(body.get("tenant_id") or "")
    )
    if not tid:
        raise HTTPException(status_code=400, detail="tenant_id_required")
    window = int(body.get("window_hours") or 24)
    include_live = body.get("include_live")
    if include_live is None:
        include_live = True
    out = evaluate_knowledge_slo_wiring_gate(
        tid,
        domain_id=str(body.get("domain_id") or ""),
        window_hours=window,
        include_live=bool(include_live),
    )
    if out.get("status") == "error":
        raise HTTPException(status_code=400, detail=out.get("reason") or "error")
    return out


@router.post("/slo/evaluate-attainment")
async def slo_evaluate_attainment_route(
    request: Request,
    x_aiplat_tenant_id: Optional[str] = Header(None, alias="X-AIPLAT-TENANT-ID"),
) -> Dict[str, Any]:
    """评估 SLO 生产达标窗口（attainment_ok；certified 恒假）。

    Args:
        request: FastAPI Request（JSON：tenant_id/domain_id/window_hours/
            min_samples/approval_record_path/include_live）。
        x_aiplat_tenant_id: 租户 header。
    """
    from core.api.core_facade import evaluate_knowledge_slo_attainment_window

    body: Dict[str, Any] = {}
    try:
        raw = await request.json()
        if isinstance(raw, dict):
            body = raw
    except Exception:
        body = {}

    tid = _tenant_from(
        request, x_aiplat_tenant_id, str(body.get("tenant_id") or "")
    )
    if not tid:
        raise HTTPException(status_code=400, detail="tenant_id_required")
    window = int(body.get("window_hours") or 24)
    min_samples = int(body.get("min_samples") or 1)
    include_live = body.get("include_live")
    if include_live is None:
        include_live = True
    approval = body.get("approval_record_path")
    out = evaluate_knowledge_slo_attainment_window(
        tid,
        domain_id=str(body.get("domain_id") or ""),
        window_hours=window,
        include_live=bool(include_live),
        min_samples=min_samples,
        approval_record_path=str(approval) if approval else None,
    )
    if out.get("status") == "error":
        raise HTTPException(status_code=400, detail=out.get("reason") or "error")
    return out


@router.post("/slo/evaluate-alerts")
async def slo_evaluate_alerts_route(
    request: Request,
    x_aiplat_tenant_id: Optional[str] = Header(None, alias="X-AIPLAT-TENANT-ID"),
) -> Dict[str, Any]:
    """SLO residual：告警候选（非投递；certified 恒假）。

    Args:
        request: FastAPI Request（JSON：tenant_id/domain_id/window_hours/include_live）。
        x_aiplat_tenant_id: 租户 header。
    """
    from core.api.core_facade import evaluate_knowledge_slo_alert_candidates

    body: Dict[str, Any] = {}
    try:
        raw = await request.json()
        if isinstance(raw, dict):
            body = raw
    except Exception:
        body = {}

    tid = _tenant_from(
        request, x_aiplat_tenant_id, str(body.get("tenant_id") or "")
    )
    if not tid:
        raise HTTPException(status_code=400, detail="tenant_id_required")
    window = int(body.get("window_hours") or 24)
    include_live = body.get("include_live")
    if include_live is None:
        include_live = True
    out = evaluate_knowledge_slo_alert_candidates(
        tid,
        domain_id=str(body.get("domain_id") or ""),
        window_hours=window,
        include_live=bool(include_live),
    )
    if out.get("status") == "invalid":
        raise HTTPException(status_code=400, detail=out.get("error") or "invalid")
    return out


@router.post("/slo/sample")
async def slo_record_sample_route(
    request: Request,
    x_aiplat_tenant_id: Optional[str] = Header(None, alias="X-AIPLAT-TENANT-ID"),
) -> Dict[str, Any]:
    """写入一条 SLO 样本（测试/运维注入；生产热路径另有 Facade 钩子）。

    Args:
        request: FastAPI Request JSON（metric/value/tenant_id/...）。
        x_aiplat_tenant_id: 租户 header。
    """
    from core.api.core_facade import record_knowledge_slo_sample

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="invalid_json")

    tid = _tenant_from(
        request, x_aiplat_tenant_id, str(body.get("tenant_id") or "")
    )
    if not tid:
        raise HTTPException(status_code=400, detail="tenant_id_required")
    metric = str(body.get("metric") or "").strip()
    if not metric:
        raise HTTPException(status_code=400, detail="metric_required")
    try:
        value = float(body.get("value"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="value_not_numeric")

    out = record_knowledge_slo_sample(
        metric,
        value,
        tenant_id=tid,
        domain_id=str(body.get("domain_id") or ""),
        source=str(body.get("source") or "fde.slo.sample"),
        ok=bool(body.get("ok", True)),
    )
    if out.get("status") == "error":
        raise HTTPException(status_code=400, detail=out.get("reason") or "error")
    return out
