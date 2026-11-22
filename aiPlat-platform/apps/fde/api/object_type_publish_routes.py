"""FDE N02 ObjectType 人审发布 — 薄路由，经 CoreFacade。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-object-type-publish"])


class ObjectTypeDraftBody(BaseModel):
    """提交 ObjectType 草稿。"""

    object_type_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    definition: Dict[str, Any] = Field(default_factory=dict)
    actor: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)


class ObjectTypeTransitionBody(BaseModel):
    """ObjectType 状态转换。"""

    to_status: str = Field(..., min_length=1)
    actor: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    role: str = Field(
        "",
        description="caller role for N02 publish RBAC (required on publish)",
    )


class ObjectTypeGateBody(BaseModel):
    """门槛门探针（可选附带 suite）。"""

    suite: Optional[Dict[str, Any]] = None


@router.post("/object-types/drafts")
async def submit_object_type_draft_route(
    body: ObjectTypeDraftBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """提交 ObjectType 草稿。

    Args:
        body: 草稿载荷。
        tenant_id: 租户。
    """
    from core.api.core_facade import submit_object_type_draft

    try:
        return submit_object_type_draft(
            tenant_id=tenant_id,
            object_type_id=body.object_type_id,
            version=body.version,
            definition=body.definition,
            actor=body.actor,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/object-types/{object_type_id}/versions/{version}/transition")
async def transition_object_type_route(
    object_type_id: str,
    version: str,
    body: ObjectTypeTransitionBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """ObjectType 状态转换（publish 须 role）。

    Args:
        object_type_id: 类型 id。
        version: 版本。
        body: 转换载荷。
        tenant_id: 租户。
    """
    from core.api.core_facade import transition_object_type

    try:
        return transition_object_type(
            tenant_id=tenant_id,
            object_type_id=object_type_id,
            version=version,
            to_status=body.to_status,
            actor=body.actor,
            reason=body.reason,
            role=body.role,
        )
    except ValueError as exc:
        msg = str(exc)
        code = 403 if "rbac denied" in msg else 400
        raise HTTPException(status_code=code, detail=msg) from exc


@router.get("/object-types/{object_type_id}")
async def get_published_object_type_route(
    object_type_id: str,
    tenant_id: str = Query(..., description="tenant id (required)"),
    version: Optional[str] = Query(None),
):
    """读取已发布 ObjectType。

    Args:
        object_type_id: 类型 id。
        tenant_id: 租户。
        version: 可选版本。
    """
    from core.api.core_facade import get_published_object_type

    out = get_published_object_type(
        tenant_id=tenant_id,
        object_type_id=object_type_id,
        version=version,
    )
    if not out:
        raise HTTPException(status_code=404, detail="object_type_not_published")
    return out


@router.get("/object-types")
async def list_object_type_versions_route(
    tenant_id: str = Query(..., description="tenant id (required)"),
    object_type_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """列出 ObjectType 版本行。

    Args:
        tenant_id: 租户。
        object_type_id: 可选类型过滤。
        status: 可选状态过滤。
        limit: 条数上限。
    """
    from core.api.core_facade import list_object_type_versions

    return {
        "items": list_object_type_versions(
            tenant_id=tenant_id,
            object_type_id=object_type_id or "",
            status=status or "",
            limit=limit,
        )
    }


@router.post("/object-types/suite")
async def run_object_type_publish_suite_route():
    """运行 N02 ObjectType 人审发布套件。"""
    from core.api.core_facade import run_object_type_publish_suite

    return run_object_type_publish_suite()


@router.post("/object-types/gate")
async def evaluate_object_type_publish_gate_route(
    body: ObjectTypeGateBody = Body(default_factory=ObjectTypeGateBody),
):
    """评估 N02 ObjectType 人审发布门槛门。

    Args:
        body: 可选 suite 回执。
    """
    from core.api.core_facade import (
        evaluate_object_type_publish_gate,
        run_object_type_publish_suite,
    )

    suite = body.suite if body.suite is not None else run_object_type_publish_suite()
    return evaluate_object_type_publish_gate(suite)
