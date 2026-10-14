"""Delivery report APIs — cost narrative page (HYBRID_ENTERPRISE_DELIVERY §4)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Response

from auth.deps import require_auth
from api.schemas_response import StatusResponse
from delivery.cost_report import build_delivery_cost_report, render_cost_report_markdown

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
    # StatusResponse allows extra fields
    out = dict(report)
    out["status"] = "ok"
    return out
