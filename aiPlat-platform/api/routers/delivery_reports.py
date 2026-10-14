"""Delivery report APIs — cost narrative + KB health (HYBRID_ENTERPRISE_DELIVERY §4 / KB_HEALTH)."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response

from auth.deps import require_auth
from api.schemas_response import StatusResponse
from delivery.cost_report import (
    build_delivery_cost_report,
    kb_cache_stats,
    render_cost_report_markdown,
)
from delivery.kb_health import (
    build_kb_health_report,
    kb_low_confidence_top,
    kb_miss_top,
    render_kb_health_markdown,
)
from delivery.kb_health_archive import (
    archive_interval_hours,
    archive_kb_health_report,
    list_kb_health_archives,
    read_kb_health_archive,
)
from delivery.monthly_ops_report import (
    build_monthly_ops_report,
    render_monthly_ops_markdown,
)
from delivery.l3_duty_desk import (
    build_l3_duty_desk,
    render_l3_duty_markdown,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/platform", tags=["delivery"])


@router.get("/delivery/cost-report", response_model=StatusResponse)
async def get_delivery_cost_report(
    tenant_id: str = Query(default="default"),
    window_hours: int = Query(default=720, ge=1, le=8760),
    project_id: str = Query(default=""),
    format: Optional[str] = Query(default="json", description="json | markdown"),
    _auth: str = Depends(require_auth),
):
    """Customer-facing cost page data: cache hits, call volume, routing policy, optional ¥."""
    report = build_delivery_cost_report(
        tenant_id=tenant_id,
        window_hours=window_hours,
        project_id=project_id,
    )
    if (format or "").lower() in ("md", "markdown", "text"):
        body = render_cost_report_markdown(report)
        return Response(content=body, media_type="text/markdown; charset=utf-8")
    out = dict(report)
    out["status"] = "ok"
    return out


@router.get("/delivery/monthly-ops-report", response_model=StatusResponse)
async def get_delivery_monthly_ops_report(
    tenant_id: str = Query(default="default"),
    window_hours: int = Query(default=720, ge=1, le=8760),
    project_id: str = Query(default=""),
    collection_id: str = Query(default="default"),
    format: Optional[str] = Query(default="json", description="json | markdown"),
    _auth: str = Depends(require_auth),
):
    """L1 monthly ops report: daemon + cost + KB health (DELIVERY §5)."""
    report = build_monthly_ops_report(
        tenant_id=tenant_id,
        window_hours=window_hours,
        project_id=project_id,
        collection_id=collection_id,
    )
    if (format or "").lower() in ("md", "markdown", "text"):
        body = render_monthly_ops_markdown(report)
        return Response(content=body, media_type="text/markdown; charset=utf-8")
    out = dict(report)
    out["status"] = "ok"
    return out


@router.get("/delivery/l3-duty-desk", response_model=StatusResponse)
async def get_delivery_l3_duty_desk(
    tenant_id: str = Query(default="default"),
    window_hours: int = Query(default=720, ge=1, le=8760),
    project_id: str = Query(default=""),
    format: Optional[str] = Query(default="json", description="json | markdown"),
    _auth: str = Depends(require_auth),
):
    """L3 duty desk: contact + eval observability + miss/low signals + tips."""
    report = build_l3_duty_desk(
        tenant_id=tenant_id,
        window_hours=window_hours,
        project_id=project_id,
    )
    if (format or "").lower() in ("md", "markdown", "text"):
        body = render_l3_duty_markdown(report)
        return Response(content=body, media_type="text/markdown; charset=utf-8")
    out = dict(report)
    out["status"] = "ok"
    return out


@router.get("/delivery/kb-health", response_model=StatusResponse)
async def get_delivery_kb_health(
    tenant_id: str = Query(default="default"),
    collection_id: str = Query(default="default"),
    window_hours: int = Query(default=168, ge=1, le=8760),
    project_id: str = Query(default=""),
    format: Optional[str] = Query(default="json", description="json | markdown"),
    _auth: str = Depends(require_auth),
):
    """Customer-facing KB health score panel (metrics → suggestions)."""
    report = build_kb_health_report(
        tenant_id=tenant_id,
        collection_id=collection_id,
        window_hours=window_hours,
        project_id=project_id,
    )
    if (format or "").lower() in ("md", "markdown", "text"):
        body = render_kb_health_markdown(report)
        return Response(content=body, media_type="text/markdown; charset=utf-8")
    out = dict(report)
    out["status"] = "ok"
    return out


@router.get("/kb/miss-top", response_model=StatusResponse)
async def get_kb_miss_top(
    tenant_id: str = Query(default="default"),
    hours: int = Query(default=168, ge=1, le=8760),
    limit: int = Query(default=5, ge=1, le=50),
    _auth: str = Depends(require_auth),
):
    """漏召 TOP — best-effort from syscall_events (KB_HEALTH §3.2.1)."""
    body = kb_miss_top(tenant_id=tenant_id, window_hours=hours, limit=limit)
    out = dict(body)
    out["status"] = "ok"
    out["tenant_id"] = tenant_id
    return out


@router.get("/kb/low-confidence-top", response_model=StatusResponse)
async def get_kb_low_confidence_top(
    tenant_id: str = Query(default="default"),
    hours: int = Query(default=168, ge=1, le=8760),
    limit: int = Query(default=5, ge=1, le=50),
    threshold: float = Query(default=0.5, ge=0.0, le=1.0),
    _auth: str = Depends(require_auth),
):
    """低置信 TOP — best-effort from syscall_events (KB_HEALTH §3.2.2)."""
    body = kb_low_confidence_top(
        tenant_id=tenant_id,
        window_hours=hours,
        limit=limit,
        threshold=threshold,
    )
    out = dict(body)
    out["status"] = "ok"
    out["tenant_id"] = tenant_id
    return out


@router.get("/kb/cache-stats", response_model=StatusResponse)
async def get_kb_cache_stats(
    tenant_id: str = Query(default="default"),
    hours: int = Query(default=168, ge=1, le=8760),
    _auth: str = Depends(require_auth),
):
    """缓存命中率 — semantic_cache.stats (KB_HEALTH §3.2.3). ``hours`` reserved."""
    _ = hours
    body = kb_cache_stats(tenant_id=tenant_id)
    out = dict(body)
    out["status"] = "ok"
    out["tenant_id"] = tenant_id
    return out


@router.post("/delivery/kb-health/archive", response_model=StatusResponse)
async def post_kb_health_archive(
    tenant_id: str = Query(default="default"),
    collection_id: str = Query(default="default"),
    window_hours: int = Query(default=168, ge=1, le=8760),
    project_id: str = Query(default=""),
    force: bool = Query(default=False),
    _auth: str = Depends(require_auth),
):
    """Manually archive this ISO week's KB health markdown (governance reports)."""
    result = await asyncio.to_thread(
        archive_kb_health_report,
        tenant_id=tenant_id,
        collection_id=collection_id,
        window_hours=window_hours,
        project_id=project_id,
        force=force,
    )
    out = dict(result)
    out["status"] = "ok" if result.get("ok") else "error"
    return out


@router.get("/governance/reports", response_model=StatusResponse)
async def list_governance_kb_health_reports(
    limit: int = Query(default=52, ge=1, le=200),
    _auth: str = Depends(require_auth),
):
    """List archived ``kb-health-YYYY-WW.md`` files."""
    body = list_kb_health_archives(limit=limit)
    out = dict(body)
    out["status"] = "ok"
    return out


@router.get("/governance/reports/kb-health/{week}", response_model=StatusResponse)
async def get_governance_kb_health_report(
    week: str,
    format: Optional[str] = Query(default="json", description="json | markdown"),
    _auth: str = Depends(require_auth),
):
    """Fetch archived weekly KB health report (file: kb-health-{YYYY-WW}.md)."""
    body = read_kb_health_archive(week)
    if not body.get("ok"):
        out = dict(body)
        out["status"] = "not_found"
        return out
    if (format or "").lower() in ("md", "markdown", "text"):
        return Response(
            content=str(body.get("markdown") or ""),
            media_type="text/markdown; charset=utf-8",
        )
    out = dict(body)
    out["status"] = "ok"
    return out


async def _kb_health_archive_cron_loop(interval_hours: float) -> None:
    await asyncio.sleep(90)  # let platform settle
    while True:
        try:
            result = await asyncio.to_thread(archive_kb_health_report)
            if result.get("skipped"):
                logger.debug("KB health archive skipped: %s", result.get("reason"))
            else:
                logger.info(
                    "KB health archived week=%s path=%s score=%s",
                    result.get("week"),
                    result.get("path"),
                    result.get("health_score"),
                )
        except Exception:
            logger.debug("KB health archive cron failed", exc_info=True)
        await asyncio.sleep(max(3600.0, float(interval_hours) * 3600.0))


@router.on_event("startup")
async def _start_kb_health_archive_cron() -> None:
    hours = archive_interval_hours()
    if hours <= 0:
        logger.info("KB health archive cron disabled (AIPLAT_KB_HEALTH_ARCHIVE_HOURS=%s)", hours)
        return
    asyncio.create_task(_kb_health_archive_cron_loop(hours))
    logger.info("KB health archive cron started (interval=%sh)", hours)
