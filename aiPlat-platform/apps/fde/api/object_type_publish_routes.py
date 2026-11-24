"""FDE N02 ObjectType 人审发布 — 薄路由，经 CoreFacade。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

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


class ObjectTypeBulkItem(BaseModel):
    """批量转换单项。"""

    tenant_id: str = Field(..., min_length=1)
    object_type_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    to_status: str = Field(..., min_length=1)


class ObjectTypeBulkBody(BaseModel):
    """N02 residual：多租户批量状态转换（非种子替换）。"""

    items: List[ObjectTypeBulkItem] = Field(default_factory=list)
    actor: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    role: str = Field(
        "",
        description="caller role for N02 publish RBAC (required when any item publishes)",
    )


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


@router.post("/object-types/bulk-transition")
async def bulk_transition_object_types_route(
    body: ObjectTypeBulkBody = Body(...),
):
    """N02 residual：多租户批量状态转换（非种子替换 / 非 certified）。

    Args:
        body: items + actor/reason/role。
    """
    from core.api.core_facade import bulk_transition_object_types

    try:
        return bulk_transition_object_types(
            [item.model_dump() for item in body.items],
            actor=body.actor,
            reason=body.reason,
            role=body.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class ObjectTypeSeedAuthorityBody(BaseModel):
    """N02 residual：published 覆盖 seed 权威解析。"""

    tenant_id: str = Field(..., min_length=1)
    seed_path: str = Field(..., min_length=1)
    object_type_ids: Optional[List[str]] = None
    output_root: Optional[str] = None
    write: bool = False


@router.post("/object-types/seed-authority")
async def apply_published_seed_authority_route(
    body: ObjectTypeSeedAuthorityBody = Body(...),
):
    """N02 residual：有界 published-over-seed（非全量种子替换 / 非 certified）。

    Args:
        body: 租户 + 种子路径 + 可选类型列表。
    """
    from core.api.core_facade import apply_published_seed_authority

    out = apply_published_seed_authority(
        tenant_id=body.tenant_id,
        seed_path=body.seed_path,
        object_type_ids=body.object_type_ids,
        output_root=body.output_root,
        write=body.write,
    )
    if out.get("status") == "invalid":
        raise HTTPException(status_code=400, detail=out.get("error") or "invalid")
    return out


@router.post("/object-types/seed-authority/suite")
async def run_seed_replacement_suite_route():
    """N02 residual：种子权威覆盖套件。"""
    from core.api.core_facade import run_seed_replacement_suite

    return run_seed_replacement_suite()


@router.post("/object-types/seed-authority/gate")
async def evaluate_seed_replacement_gate_route(
    body: ObjectTypeGateBody = Body(default_factory=ObjectTypeGateBody),
):
    """N02 residual：种子权威覆盖门槛门。

    Args:
        body: 可选 suite 回执。
    """
    from core.api.core_facade import (
        evaluate_seed_replacement_gate,
        run_seed_replacement_suite,
    )

    suite = body.suite if body.suite is not None else run_seed_replacement_suite()
    return evaluate_seed_replacement_gate(suite)


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
