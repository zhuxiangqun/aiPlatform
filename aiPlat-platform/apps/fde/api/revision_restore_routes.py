"""FDE N24 Revision Restore HTTP — 薄路由，经 CoreFacade（非管理端回滚 UI）。"""
from __future__ import annotations

from typing import Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-revision-restore"])


class RestoreRequestBody(BaseModel):
    """提交审批式 restore 请求。"""

    entity_type: str = Field(..., min_length=1)
    entity_id: str = Field(..., min_length=1)
    target_revision: int = Field(..., ge=1)
    requester: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)


class RestoreDecisionBody(BaseModel):
    """批准或拒绝 restore 请求。"""

    actor: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)


class RestoreApprovalGateBody(BaseModel):
    """门槛门探针（透传 suite）。"""

    suite: Optional[Dict] = None


def _http_from_ledger(exc: Exception) -> HTTPException:
    """将 FactLedger/ValueError 映射为 400。

    Args:
        exc: 账本或校验异常。
    """
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/revision-restore/requests")
async def list_revision_restore_requests_route(
    tenant_id: str = Query(..., description="tenant id (required)"),
    status: str = Query("", description="optional status filter"),
    entity_type: str = Query("", description="optional entity type"),
    entity_id: str = Query("", description="optional entity id"),
    limit: int = Query(100, ge=1, le=500),
):
    """列出审批式 restore 请求。

    Args:
        tenant_id: 租户。
        status: 可选状态。
        entity_type: 可选实体类型。
        entity_id: 可选实体 ID。
        limit: 最大条数。
    """
    from core.api.core_facade import fact_ledger_list_revision_restore_requests

    try:
        rows = await fact_ledger_list_revision_restore_requests(
            tenant_id=tenant_id,
            status=status,
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
        )
    except ValueError as exc:
        raise _http_from_ledger(exc) from exc
    return {"requests": rows}


@router.post("/revision-restore/requests")
async def request_revision_restore_route(
    body: RestoreRequestBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """提交审批式 restore 请求。

    Args:
        body: 实体与目标修订。
        tenant_id: 租户。
    """
    from core.api.core_facade import fact_ledger_request_revision_restore

    try:
        return await fact_ledger_request_revision_restore(
            tenant_id=tenant_id,
            entity_type=body.entity_type,
            entity_id=body.entity_id,
            target_revision=body.target_revision,
            requester=body.requester,
            reason=body.reason,
        )
    except ValueError as exc:
        raise _http_from_ledger(exc) from exc


@router.post("/revision-restore/requests/{request_id}/approve")
async def approve_revision_restore_route(
    request_id: str,
    body: RestoreDecisionBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """批准并执行 restore（审批人 ≠ 请求人）。

    Args:
        request_id: 请求 ID。
        body: 审批人与理由。
        tenant_id: 租户。
    """
    from core.api.core_facade import fact_ledger_approve_revision_restore

    try:
        return await fact_ledger_approve_revision_restore(
            request_id=request_id,
            tenant_id=tenant_id,
            approver=body.actor,
            reason=body.reason,
        )
    except ValueError as exc:
        raise _http_from_ledger(exc) from exc


@router.post("/revision-restore/requests/{request_id}/reject")
async def reject_revision_restore_route(
    request_id: str,
    body: RestoreDecisionBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """拒绝 pending restore 请求。

    Args:
        request_id: 请求 ID。
        body: 拒绝人与理由。
        tenant_id: 租户。
    """
    from core.api.core_facade import fact_ledger_reject_revision_restore

    try:
        return await fact_ledger_reject_revision_restore(
            request_id=request_id,
            tenant_id=tenant_id,
            rejector=body.actor,
            reason=body.reason,
        )
    except ValueError as exc:
        raise _http_from_ledger(exc) from exc


@router.get("/revision-restore/audit")
async def list_revision_audit_route(
    tenant_id: str = Query(..., description="tenant id (required)"),
    entity_type: str = Query("", description="optional entity type"),
    entity_id: str = Query("", description="optional entity id"),
    event_type: str = Query("", description="optional event type"),
    limit: int = Query(100, ge=1, le=500),
):
    """列出 revision_audit 事件（账本内；非统一总线）。

    Args:
        tenant_id: 租户。
        entity_type: 可选实体类型。
        entity_id: 可选实体 ID。
        event_type: 可选事件类型。
        limit: 最大条数。
    """
    from core.api.core_facade import fact_ledger_list_revision_audit

    try:
        rows = await fact_ledger_list_revision_audit(
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            limit=limit,
        )
    except ValueError as exc:
        raise _http_from_ledger(exc) from exc
    return {"events": rows}


@router.get("/revision-restore/action-bridges")
async def list_revision_action_bridges_route(
    tenant_id: str = Query(..., description="tenant id (required)"),
    entity_type: str = Query("", description="optional entity type"),
    entity_id: str = Query("", description="optional entity id"),
    limit: int = Query(100, ge=1, le=500),
):
    """列出 revision→ActionExecution 桥接行。

    Args:
        tenant_id: 租户。
        entity_type: 可选实体类型。
        entity_id: 可选实体 ID。
        limit: 最大条数。
    """
    from core.api.core_facade import fact_ledger_list_revision_action_bridges

    try:
        rows = await fact_ledger_list_revision_action_bridges(
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
        )
    except ValueError as exc:
        raise _http_from_ledger(exc) from exc
    return {"bridges": rows}


@router.post("/revision-restore/suite")
async def run_restore_approval_suite_route(
    tenant_id: str = Query("n24-restore-appr-http", description="suite tenant"),
    domain_id: str = Query("", description="optional domain"),
):
    """运行审批式 Restore 加深套件（certified 恒 false）。

    Args:
        tenant_id: 写入租户。
        domain_id: 可选域。
    """
    from core.api.core_facade import fact_ledger_run_restore_approval_suite

    return await fact_ledger_run_restore_approval_suite(
        tenant_id=tenant_id, domain_id=domain_id
    )


@router.post("/revision-restore/gate")
async def evaluate_restore_approval_gate_route(
    body: RestoreApprovalGateBody = Body(default_factory=RestoreApprovalGateBody),
):
    """评估审批式 Restore 门槛门（certified 恒 false）。

    Args:
        body: 可选 suite 透传。
    """
    from core.api.core_facade import evaluate_fact_restore_approval_gate

    return evaluate_fact_restore_approval_gate(suite=body.suite)
