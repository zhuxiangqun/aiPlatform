"""FDE Ontology Package — 薄路由，经 CoreFacade（版本/校验/兼容/回滚）。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-ontology-packages"])


class PackagePublishBody(BaseModel):
    """发布 Ontology Package。"""

    package_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    schema_types: List[str] = Field(default_factory=list, alias="schema")
    actions: List[str] = Field(default_factory=list)
    functions: List[str] = Field(default_factory=list)
    interfaces: List[str] = Field(default_factory=list)
    dependencies: List[Dict[str, Any]] = Field(default_factory=list)
    compatibility: Dict[str, Any] = Field(default_factory=dict)
    migrations: List[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class PackageCompatBody(BaseModel):
    """兼容性检查。"""

    from_version: str = Field(..., min_length=1)
    to_version: str = Field(..., min_length=1)


class PackageRollbackBody(BaseModel):
    """回滚到指定版本。"""

    to_version: str = Field(..., min_length=1)


@router.post("/ontology-packages")
async def publish_ontology_package_route(
    body: PackagePublishBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """发布 Ontology Package 版本。

    Args:
        body: 包元数据。
        tenant_id: 租户。
    """
    from core.api.core_facade import publish_ontology_package

    out = publish_ontology_package(
        tenant_id=tenant_id,
        package_id=body.package_id,
        version=body.version,
        schema=body.schema_types,
        actions=body.actions,
        functions=body.functions,
        interfaces=body.interfaces,
        dependencies=body.dependencies,
        compatibility=body.compatibility,
        migrations=body.migrations,
    )
    if out.get("status") == "invalid":
        raise HTTPException(status_code=400, detail=out.get("error") or "invalid")
    if out.get("status") == "conflict":
        raise HTTPException(status_code=409, detail=out.get("error") or "conflict")
    return out


@router.get("/ontology-packages/{package_id}")
async def get_ontology_package_route(
    package_id: str,
    tenant_id: str = Query(..., description="tenant id (required)"),
    version: Optional[str] = Query(None),
):
    """读取 Ontology Package（租户隔离）。

    Args:
        package_id: 包 id。
        tenant_id: 租户。
        version: 可选版本。
    """
    from core.api.core_facade import get_ontology_package

    out = get_ontology_package(package_id, tenant_id=tenant_id, version=version)
    if not out:
        raise HTTPException(status_code=404, detail="package_not_found")
    return out


@router.post("/ontology-packages/{package_id}/validate")
async def validate_ontology_package_route(
    package_id: str,
    tenant_id: str = Query(..., description="tenant id (required)"),
    version: Optional[str] = Query(None),
):
    """校验包可验证。

    Args:
        package_id: 包 id。
        tenant_id: 租户。
        version: 可选版本。
    """
    from core.api.core_facade import validate_ontology_package

    return validate_ontology_package(
        package_id, tenant_id=tenant_id, version=version
    )


@router.post("/ontology-packages/{package_id}/compatibility")
async def check_ontology_package_compatibility_route(
    package_id: str,
    body: PackageCompatBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """检查版本兼容矩阵。

    Args:
        package_id: 包 id。
        body: from/to 版本。
        tenant_id: 租户。
    """
    from core.api.core_facade import check_ontology_package_compatibility

    out = check_ontology_package_compatibility(
        package_id,
        tenant_id=tenant_id,
        from_version=body.from_version,
        to_version=body.to_version,
    )
    if out.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=out.get("error") or "not_found")
    return out


@router.post("/ontology-packages/{package_id}/dependencies/check")
async def check_ontology_package_dependencies_route(
    package_id: str,
    tenant_id: str = Query(..., description="tenant id (required)"),
    version: Optional[str] = Query(None),
):
    """检查依赖锁定。

    Args:
        package_id: 包 id。
        tenant_id: 租户。
        version: 可选版本。
    """
    from core.api.core_facade import check_ontology_package_dependencies

    return check_ontology_package_dependencies(
        package_id, tenant_id=tenant_id, version=version
    )


@router.post("/ontology-packages/{package_id}/rollback")
async def rollback_ontology_package_route(
    package_id: str,
    body: PackageRollbackBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """回滚 active 版本。

    Args:
        package_id: 包 id。
        body: 目标版本。
        tenant_id: 租户。
    """
    from core.api.core_facade import rollback_ontology_package

    out = rollback_ontology_package(
        package_id, tenant_id=tenant_id, to_version=body.to_version
    )
    if out.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=out.get("error") or "not_found")
    if out.get("status") == "invalid":
        raise HTTPException(status_code=400, detail=out.get("error") or "invalid")
    return out
