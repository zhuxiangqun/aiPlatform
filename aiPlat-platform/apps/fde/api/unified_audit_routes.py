"""FDE N24 Unified Audit View HTTP — 薄路由，经 CoreFacade（非全量写总线）。"""
from __future__ import annotations

from typing import Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(tags=["fde-unified-audit"])


class UnifiedAuditGateBody(BaseModel):
    """门槛门探针（透传 suite）。"""

    suite: Optional[Dict] = None


def _http_from_err(exc: Exception) -> HTTPException:
    """将校验异常映射为 400。

    Args:
        exc: 校验异常。
    """
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/unified-audit")
async def list_unified_audit_route(
    tenant_id: str = Query(..., description="tenant id (required)"),
    streams: str = Query("", description="comma-separated streams"),
    package_id: str = Query("", description="optional package filter"),
    action_id_prefix: str = Query("", description="optional action_id prefix"),
    entity_type: str = Query("", description="optional revision entity type"),
    entity_id: str = Query("", description="optional revision entity id"),
    limit: int = Query(100, ge=1, le=500),
):
    """只读汇合 Package / ActionExecution / revision_audit。

    Args:
        tenant_id: 租户。
        streams: 逗号分隔流名。
        package_id: 可选包过滤。
        action_id_prefix: 可选 action 前缀。
        entity_type: 可选实体类型。
        entity_id: 可选实体 ID。
        limit: 最大条数。
    """
    from core.api.core_facade import list_fact_unified_audit_events

    try:
        return await list_fact_unified_audit_events(
            tenant_id=tenant_id,
            streams=streams,
            package_id=package_id,
            action_id_prefix=action_id_prefix,
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
        )
    except ValueError as exc:
        raise _http_from_err(exc) from exc


@router.post("/unified-audit/suite")
async def run_unified_audit_suite_route(
    tenant_id: str = Query("n24-unified-audit-tenant", description="suite tenant"),
    domain_id: str = Query("", description="optional domain"),
):
    """运行统一审计视图套件（certified 恒 false）。

    Args:
        tenant_id: 写入租户。
        domain_id: 可选域。
    """
    from core.api.core_facade import run_fact_unified_audit_view_suite

    return await run_fact_unified_audit_view_suite(
        tenant_id=tenant_id, domain_id=domain_id
    )


@router.post("/unified-audit/gate")
async def evaluate_unified_audit_gate_route(
    body: UnifiedAuditGateBody = Body(default_factory=UnifiedAuditGateBody),
):
    """评估统一审计视图门槛门（certified 恒 false）。

    Args:
        body: 可选 suite 透传。
    """
    from core.api.core_facade import evaluate_fact_unified_audit_view_gate

    return evaluate_fact_unified_audit_view_gate(suite=body.suite)
