"""FDE N18 部署侧 RBAC — 薄路由，经 CoreFacade。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-deployed-rbac"])


class PermissionBody(BaseModel):
    """权限评估。"""

    role: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    actor_tenant: str = Field(..., min_length=1)
    target_tenant: str = Field(..., min_length=1)
    policy_json: Optional[str] = None


class GateBody(BaseModel):
    """门槛门探针。"""

    suite: Optional[Dict[str, Any]] = None


@router.post("/deployed-rbac/permission")
async def evaluate_deployed_rbac_permission_route(
    body: PermissionBody = Body(...),
):
    """评估部署侧权限。

    Args:
        body: role/action/tenants。
    """
    from core.api.core_facade import evaluate_deployed_rbac_permission

    try:
        return evaluate_deployed_rbac_permission(
            role=body.role,
            action=body.action,
            actor_tenant=body.actor_tenant,
            target_tenant=body.target_tenant,
            policy_json=body.policy_json,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/deployed-rbac/suite")
async def run_deployed_rbac_suite_route():
    """运行部署侧 RBAC 套件。"""
    from core.api.core_facade import run_deployed_rbac_suite

    return run_deployed_rbac_suite()


@router.post("/deployed-rbac/gate")
async def evaluate_deployed_rbac_gate_route(
    body: GateBody = Body(default_factory=GateBody),
):
    """部署侧 RBAC 门槛门。

    Args:
        body: 可选 suite 回执。
    """
    from core.api.core_facade import (
        evaluate_deployed_rbac_gate,
        run_deployed_rbac_suite,
    )

    suite = body.suite
    if suite is None:
        suite = run_deployed_rbac_suite()
    return evaluate_deployed_rbac_gate(suite)
