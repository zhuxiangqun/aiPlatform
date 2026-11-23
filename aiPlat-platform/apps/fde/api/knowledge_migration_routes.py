"""FDE Knowledge Migration — 薄路由，经 CoreFacade（W10 / §15）。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-knowledge-migration"])


class MigrationStartBody(BaseModel):
    """启动迁移作业。"""

    domain: str = Field(..., min_length=1)
    mapping: Optional[Dict[str, Any]] = None
    job_id: Optional[str] = None


class DualWriteBody(BaseModel):
    """双写一条记录。"""

    record_key: str = Field(..., min_length=1)
    payload: Dict[str, Any] = Field(default_factory=dict)
    fail_target: bool = False


class ReconcileBody(BaseModel):
    """对账请求。"""

    repair: bool = False


class ReadPointerBody(BaseModel):
    """读指针。"""

    pointer: str = Field(..., min_length=1)


class RollbackDrillBody(BaseModel):
    """回滚演练。"""

    note: str = ""


class ProductionAttestBody(BaseModel):
    """N11 residual：生产切写就绪回执（非 certified）。"""

    actor: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    raw_fact_index_ok: Optional[bool] = Field(
        None,
        description="可选 Raw↔Fact↔Index 对账结果；False 时阻断",
    )


@router.post("/knowledge-migrations")
async def start_knowledge_migration_route(
    body: MigrationStartBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """启动知识迁移作业。

    Args:
        body: domain/mapping。
        tenant_id: 租户。
    """
    from core.api.core_facade import start_knowledge_migration

    out = start_knowledge_migration(
        tenant_id=tenant_id,
        domain=body.domain,
        mapping=body.mapping,
        job_id=body.job_id,
    )
    if out.get("status") == "invalid":
        raise HTTPException(status_code=400, detail=out.get("error") or "invalid")
    return out


@router.get("/knowledge-migrations/{job_id}")
async def get_knowledge_migration_route(
    job_id: str,
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """读取迁移作业。

    Args:
        job_id: 作业 id。
        tenant_id: 租户。
    """
    from core.api.core_facade import get_knowledge_migration

    out = get_knowledge_migration(job_id, tenant_id=tenant_id)
    if not out:
        raise HTTPException(status_code=404, detail="migration_not_found")
    return out


@router.post("/knowledge-migrations/{job_id}/dual-write")
async def dual_write_knowledge_migration_route(
    job_id: str,
    body: DualWriteBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """双写记录。

    Args:
        job_id: 作业 id。
        body: record_key/payload。
        tenant_id: 租户。
    """
    from core.api.core_facade import dual_write_knowledge_migration

    out = dual_write_knowledge_migration(
        job_id,
        tenant_id=tenant_id,
        record_key=body.record_key,
        payload=body.payload,
        fail_target=body.fail_target,
    )
    if out.get("status") in ("invalid", "not_found"):
        raise HTTPException(
            status_code=400 if out.get("status") == "invalid" else 404,
            detail=out.get("error") or out.get("status"),
        )
    return out


@router.post("/knowledge-migrations/{job_id}/reconcile")
async def reconcile_knowledge_migration_route(
    job_id: str,
    body: ReconcileBody = Body(default_factory=ReconcileBody),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """对账（可选修复）。

    Args:
        job_id: 作业 id。
        body: repair 开关。
        tenant_id: 租户。
    """
    from core.api.core_facade import reconcile_knowledge_migration

    out = reconcile_knowledge_migration(
        job_id, tenant_id=tenant_id, repair=body.repair
    )
    if out.get("status") in ("invalid", "not_found"):
        raise HTTPException(
            status_code=400 if out.get("status") == "invalid" else 404,
            detail=out.get("error") or out.get("status"),
        )
    return out


@router.post("/knowledge-migrations/{job_id}/read-pointer")
async def set_knowledge_migration_read_pointer_route(
    job_id: str,
    body: ReadPointerBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """设置读指针。

    Args:
        job_id: 作业 id。
        body: pointer。
        tenant_id: 租户。
    """
    from core.api.core_facade import set_knowledge_migration_read_pointer

    out = set_knowledge_migration_read_pointer(
        job_id, tenant_id=tenant_id, pointer=body.pointer
    )
    if out.get("status") in ("invalid", "not_found", "blocked"):
        code = 409 if out.get("status") == "blocked" else (
            404 if out.get("status") == "not_found" else 400
        )
        raise HTTPException(status_code=code, detail=out)
    return out


@router.post("/knowledge-migrations/{job_id}/rollback-drill")
async def rollback_drill_knowledge_migration_route(
    job_id: str,
    body: RollbackDrillBody = Body(default_factory=RollbackDrillBody),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """回滚演练。

    Args:
        job_id: 作业 id。
        body: note。
        tenant_id: 租户。
    """
    from core.api.core_facade import rollback_drill_knowledge_migration

    out = rollback_drill_knowledge_migration(
        job_id, tenant_id=tenant_id, note=body.note
    )
    if out.get("status") in ("invalid", "not_found"):
        raise HTTPException(
            status_code=400 if out.get("status") == "invalid" else 404,
            detail=out.get("error") or out.get("status"),
        )
    return out


@router.post("/knowledge-migrations/{job_id}/production-attest")
async def attest_knowledge_production_cutover_route(
    job_id: str,
    body: ProductionAttestBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """N11 residual：生产切写就绪回执（非 production certified）。

    Args:
        job_id: 作业 id。
        body: actor/reason/可选 Raw↔Fact↔Index。
        tenant_id: 租户。
    """
    from core.api.core_facade import attest_knowledge_production_cutover_readiness

    out = attest_knowledge_production_cutover_readiness(
        job_id,
        tenant_id=tenant_id,
        actor=body.actor,
        reason=body.reason,
        raw_fact_index_ok=body.raw_fact_index_ok,
    )
    if out.get("status") in ("invalid", "not_found"):
        raise HTTPException(
            status_code=400 if out.get("status") == "invalid" else 404,
            detail=out.get("error") or out.get("status"),
        )
    return out


@router.get("/knowledge-migrations/{job_id}/events")
async def list_knowledge_migration_events_route(
    job_id: str,
    tenant_id: str = Query(..., description="tenant id (required)"),
    limit: int = Query(50, ge=1, le=200),
):
    """列出迁移审计事件。

    Args:
        job_id: 作业 id。
        tenant_id: 租户。
        limit: 条数。
    """
    from core.api.core_facade import list_knowledge_migration_events

    out = list_knowledge_migration_events(
        job_id, tenant_id=tenant_id, limit=limit
    )
    if out.get("status") in ("invalid", "not_found"):
        raise HTTPException(
            status_code=400 if out.get("status") == "invalid" else 404,
            detail=out.get("error") or out.get("status"),
        )
    return out
