"""FDE Knowledge Scenario — 薄路由，经 CoreFacade（模拟不写主事实）。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-scenarios"])


class ScenarioCreateBody(BaseModel):
    """创建 Scenario。"""

    branch: str = Field(..., min_length=1)
    owner: str = ""
    base_snapshot_at: str = ""
    expires_at: Optional[float] = None


class ScenarioChangeBody(BaseModel):
    """模拟变更。"""

    action: str = Field(..., min_length=1)
    target: str = ""
    params: Dict[str, Any] = Field(default_factory=dict)


class ScenarioApproveBody(BaseModel):
    """人审通过。"""

    approver: str = Field(..., min_length=1)
    approval_id: str = ""


@router.post("/scenarios")
async def create_scenario_route(
    body: ScenarioCreateBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """创建 Knowledge Scenario 分支。

    Args:
        body: 分支元数据。
        tenant_id: 租户。
    """
    from core.api.core_facade import create_knowledge_scenario

    out = create_knowledge_scenario(
        tenant_id=tenant_id,
        branch=body.branch,
        owner=body.owner,
        base_snapshot_at=body.base_snapshot_at,
        expires_at=body.expires_at,
    )
    if out.get("status") == "invalid":
        raise HTTPException(status_code=400, detail=out.get("error") or "invalid")
    if out.get("status") == "conflict":
        raise HTTPException(status_code=409, detail=out.get("error") or "conflict")
    return out


@router.get("/scenarios/{scenario_id}")
async def get_scenario_route(
    scenario_id: str,
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """读取 Scenario（租户隔离）。

    Args:
        scenario_id: 场景 id。
        tenant_id: 租户。
    """
    from core.api.core_facade import get_knowledge_scenario

    out = get_knowledge_scenario(scenario_id, tenant_id=tenant_id)
    if not out:
        raise HTTPException(status_code=404, detail="scenario_not_found")
    return out


@router.post("/scenarios/{scenario_id}/simulate")
async def simulate_scenario_route(
    scenario_id: str,
    body: ScenarioChangeBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """追加模拟变更（不写主事实）。

    Args:
        scenario_id: 场景 id。
        body: 变更。
        tenant_id: 租户。
    """
    from core.api.core_facade import simulate_knowledge_scenario_change

    out = simulate_knowledge_scenario_change(
        scenario_id=scenario_id,
        tenant_id=tenant_id,
        action=body.action,
        target=body.target,
        params=body.params,
    )
    st = out.get("status")
    if st == "not_found":
        raise HTTPException(status_code=404, detail=out.get("error") or "not_found")
    if st in ("invalid", "expired"):
        raise HTTPException(status_code=400, detail=out.get("error") or st)
    return out


@router.post("/scenarios/{scenario_id}/request-merge")
async def request_merge_route(
    scenario_id: str,
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """请求合并 → pending_review。

    Args:
        scenario_id: 场景 id。
        tenant_id: 租户。
    """
    from core.api.core_facade import request_knowledge_scenario_merge

    out = request_knowledge_scenario_merge(
        scenario_id=scenario_id, tenant_id=tenant_id
    )
    if out.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="scenario_not_found")
    if out.get("status") in ("invalid", "expired"):
        raise HTTPException(status_code=400, detail=out.get("error") or "invalid")
    return out


@router.post("/scenarios/{scenario_id}/approve-merge")
async def approve_merge_route(
    scenario_id: str,
    body: ScenarioApproveBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """人审通过合并（仍不写主事实）。

    Args:
        scenario_id: 场景 id。
        body: 审批人。
        tenant_id: 租户。
    """
    from core.api.core_facade import approve_knowledge_scenario_merge

    out = approve_knowledge_scenario_merge(
        scenario_id=scenario_id,
        tenant_id=tenant_id,
        approver=body.approver,
        approval_id=body.approval_id,
    )
    if out.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="scenario_not_found")
    if out.get("status") in ("invalid", "expired"):
        raise HTTPException(status_code=400, detail=out.get("error") or "invalid")
    return out
