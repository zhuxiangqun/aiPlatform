"""FDE Knowledge Ops Console — N24 residual 薄路由，经 CoreFacade。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-knowledge-ops-console"])


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


class OpsConsoleGateBody(BaseModel):
    """运维台 gate 请求体。"""

    suite: Optional[Dict[str, Any]] = Field(default=None)


@router.get("/ops-console/snapshot")
async def ops_console_snapshot_route(
    request: Request,
    tenant_id: Optional[str] = Query(None),
    domain_id: Optional[str] = Query(None),
    window_hours: int = Query(24, ge=1, le=720),
    include_live: bool = Query(False),
    x_aiplat_tenant_id: Optional[str] = Header(None, alias="X-AIPLAT-TENANT-ID"),
) -> Dict[str, Any]:
    """N24 residual：运维台薄壳快照（非全量；certified 恒假）。

    Args:
        request: FastAPI Request。
        tenant_id: 租户 query。
        domain_id: 可选域。
        window_hours: 窗口小时。
        include_live: SLO 是否合并 live。
        x_aiplat_tenant_id: 租户 header。
    """
    from core.api.core_facade import build_knowledge_ops_console_snapshot

    tid = _tenant_from(request, x_aiplat_tenant_id, str(tenant_id or ""))
    if not tid:
        raise HTTPException(status_code=400, detail="tenant_id_required")
    out = build_knowledge_ops_console_snapshot(
        tid,
        domain_id=str(domain_id or ""),
        window_hours=window_hours,
        include_live=include_live,
    )
    if out.get("status") == "invalid":
        raise HTTPException(status_code=400, detail=out.get("error") or "invalid")
    return out


@router.post("/ops-console/suite")
async def ops_console_suite_route() -> Dict[str, Any]:
    """N24 residual：运维台薄壳套件。"""
    from core.api.core_facade import run_knowledge_ops_console_suite

    return run_knowledge_ops_console_suite()


@router.post("/ops-console/gate")
async def ops_console_gate_route(
    body: Optional[OpsConsoleGateBody] = None,
) -> Dict[str, Any]:
    """N24 residual：运维台薄壳门槛门。

    Args:
        body: 可选已跑 suite 回执。
    """
    from core.api.core_facade import evaluate_knowledge_ops_console_gate

    suite = body.suite if body else None
    return evaluate_knowledge_ops_console_gate(suite)
