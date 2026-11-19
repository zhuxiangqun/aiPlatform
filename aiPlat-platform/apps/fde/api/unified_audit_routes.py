"""FDE N24 Unified Audit HTTP — 薄路由，经 CoreFacade（含 J5 写总线）。"""
from __future__ import annotations

from typing import Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-unified-audit"])


class UnifiedAuditGateBody(BaseModel):
    """门槛门探针（透传 suite）。"""

    suite: Optional[Dict] = None


class UnifiedAuditAppendBody(BaseModel):
    """写总线追加请求。"""

    tenant_id: str = Field(..., description="tenant id")
    event_id: str = Field(..., description="idempotent event id")
    stream: str = Field(..., description="source stream name")
    event_type: str = Field(..., description="event type")
    occurred_at: float = 0.0
    actor: str = ""
    subject: str = ""
    refs: Optional[Dict] = None
    payload: Optional[Dict] = None


class UnifiedAuditMaterializeBody(BaseModel):
    """materialize 请求。"""

    tenant_id: str = Field(..., description="tenant id")
    streams: str = ""
    package_id: str = ""
    action_id_prefix: str = ""
    entity_type: str = ""
    entity_id: str = ""
    limit: int = Field(100, ge=1, le=500)


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
    domain_id: str = Query("", description="optional ActionStore domain filter"),
    limit: int = Query(100, ge=1, le=500),
):
    """汇合 Package / ActionExecution / revision_audit / ActionStore / bus。

    Args:
        tenant_id: 租户。
        streams: 逗号分隔流名。
        package_id: 可选包过滤。
        action_id_prefix: 可选 action 前缀。
        entity_type: 可选实体类型。
        entity_id: 可选实体 ID。
        domain_id: 可选 ActionStore 域过滤。
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
            domain_id=domain_id,
            limit=limit,
        )
    except ValueError as exc:
        raise _http_from_err(exc) from exc


@router.get("/unified-audit/bus")
async def list_unified_audit_bus_route(
    tenant_id: str = Query(..., description="tenant id (required)"),
    stream: str = Query("", description="optional source stream filter"),
    event_type: str = Query("", description="optional event type"),
    limit: int = Query(100, ge=1, le=500),
):
    """列出写总线事件（租户隔离）。

    Args:
        tenant_id: 租户。
        stream: 可选源流水线。
        event_type: 可选事件类型。
        limit: 最大条数。
    """
    from core.api.core_facade import list_fact_unified_audit_bus_events

    try:
        events = list_fact_unified_audit_bus_events(
            tenant_id=tenant_id,
            stream=stream,
            event_type=event_type,
            limit=limit,
        )
        return {
            "events": events,
            "count": len(events),
            "tenant_id": tenant_id,
            "certified": False,
            "n24_full_conformance": False,
        }
    except ValueError as exc:
        raise _http_from_err(exc) from exc


@router.post("/unified-audit/append")
async def append_unified_audit_route(
    body: UnifiedAuditAppendBody = Body(...),
):
    """追加写总线事件（幂等）。

    Args:
        body: 追加载荷。
    """
    from core.api.core_facade import append_fact_unified_audit_event

    try:
        return append_fact_unified_audit_event(
            tenant_id=body.tenant_id,
            event_id=body.event_id,
            stream=body.stream,
            event_type=body.event_type,
            occurred_at=body.occurred_at,
            actor=body.actor,
            subject=body.subject,
            refs=body.refs,
            payload=body.payload,
        )
    except ValueError as exc:
        raise _http_from_err(exc) from exc


@router.post("/unified-audit/materialize")
async def materialize_unified_audit_route(
    body: UnifiedAuditMaterializeBody = Body(...),
):
    """将源三流汇合 materialize 进写总线。

    Args:
        body: materialize 参数。
    """
    from core.api.core_facade import materialize_fact_unified_audit_bus

    try:
        return await materialize_fact_unified_audit_bus(
            tenant_id=body.tenant_id,
            streams=body.streams,
            package_id=body.package_id,
            action_id_prefix=body.action_id_prefix,
            entity_type=body.entity_type,
            entity_id=body.entity_id,
            limit=body.limit,
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


@router.post("/unified-audit/bus/suite")
async def run_unified_audit_bus_suite_route(
    tenant_id: str = Query(
        "n24-unified-audit-bus-tenant", description="bus suite tenant"
    ),
    domain_id: str = Query("", description="optional domain"),
):
    """运行统一审计写总线套件（certified 恒 false）。

    Args:
        tenant_id: 写入租户。
        domain_id: 可选域。
    """
    from core.api.core_facade import run_fact_unified_audit_bus_suite

    return await run_fact_unified_audit_bus_suite(
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


@router.post("/unified-audit/bus/gate")
async def evaluate_unified_audit_bus_gate_route(
    body: UnifiedAuditGateBody = Body(default_factory=UnifiedAuditGateBody),
):
    """评估统一审计写总线门槛门（certified 恒 false）。

    Args:
        body: 可选 suite 透传。
    """
    from core.api.core_facade import evaluate_fact_unified_audit_bus_gate

    return evaluate_fact_unified_audit_bus_gate(suite=body.suite)
