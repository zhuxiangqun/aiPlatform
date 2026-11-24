"""FDE Knowledge Ops Console — N24 residual + 产品面路由，经 CoreFacade。"""
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


class OpsConsoleExportBody(BaseModel):
    """运维台有界导出请求体。"""

    tenant_id: str = Field(default="")
    domain_id: str = Field(default="")
    window_hours: int = Field(default=24, ge=1, le=720)
    include_live: bool = Field(default=False)
    write: bool = Field(default=False)
    output_root: Optional[str] = Field(default=None)


class OpsConsoleSchemaSaveBody(BaseModel):
    """运维台产品面 schema 保存请求体。"""

    tenant_id: str = Field(default="")
    object_type_id: str = Field(default="")
    definition: Dict[str, Any] = Field(default_factory=dict)
    actor: str = Field(default="ops-console-product")
    reason: str = Field(default="ops console schema editor save")
    version: str = Field(default="")


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


@router.post("/ops-console/export")
async def ops_console_export_route(
    request: Request,
    body: OpsConsoleExportBody,
    x_aiplat_tenant_id: Optional[str] = Header(None, alias="X-AIPLAT-TENANT-ID"),
) -> Dict[str, Any]:
    """N24 residual：运维台有界 JSON 导出（非全量下载；certified 恒假）。

    Args:
        request: FastAPI Request。
        body: 导出参数。
        x_aiplat_tenant_id: 租户 header。
    """
    from core.api.core_facade import export_knowledge_ops_console_snapshot

    tid = _tenant_from(request, x_aiplat_tenant_id, str(body.tenant_id or ""))
    if not tid:
        raise HTTPException(status_code=400, detail="tenant_id_required")
    out = export_knowledge_ops_console_snapshot(
        tid,
        domain_id=str(body.domain_id or ""),
        window_hours=int(body.window_hours),
        include_live=bool(body.include_live),
        output_root=body.output_root,
        write=bool(body.write),
    )
    if out.get("status") == "invalid":
        raise HTTPException(status_code=400, detail=out.get("error") or "invalid")
    if out.get("status") == "denied":
        raise HTTPException(status_code=403, detail=out.get("reason") or "denied")
    return out


@router.post("/ops-console/export/suite")
async def ops_console_export_suite_route() -> Dict[str, Any]:
    """N24 residual：运维台导出套件。"""
    from core.api.core_facade import run_knowledge_ops_console_export_suite

    return run_knowledge_ops_console_export_suite()


@router.post("/ops-console/export/gate")
async def ops_console_export_gate_route(
    body: Optional[OpsConsoleGateBody] = None,
) -> Dict[str, Any]:
    """N24 residual：运维台导出门槛门。

    Args:
        body: 可选已跑 suite 回执。
    """
    from core.api.core_facade import evaluate_knowledge_ops_console_export_gate

    suite = body.suite if body else None
    return evaluate_knowledge_ops_console_export_gate(suite)


@router.get("/ops-console/product/snapshot")
async def ops_console_product_snapshot_route(
    request: Request,
    tenant_id: Optional[str] = Query(None),
    domain_id: Optional[str] = Query(None),
    window_hours: int = Query(24, ge=1, le=720),
    include_live: bool = Query(False),
    x_aiplat_tenant_id: Optional[str] = Header(None, alias="X-AIPLAT-TENANT-ID"),
) -> Dict[str, Any]:
    """N24 产品面：运维台快照（默认可用；certified 恒假）。

    Args:
        request: FastAPI Request。
        tenant_id: 租户 query。
        domain_id: 可选域。
        window_hours: 窗口小时。
        include_live: SLO 是否合并 live。
        x_aiplat_tenant_id: 租户 header。
    """
    from core.api.core_facade import build_knowledge_ops_console_product_snapshot

    tid = _tenant_from(request, x_aiplat_tenant_id, str(tenant_id or ""))
    if not tid:
        raise HTTPException(status_code=400, detail="tenant_id_required")
    out = build_knowledge_ops_console_product_snapshot(
        tid,
        domain_id=str(domain_id or ""),
        window_hours=window_hours,
        include_live=include_live,
    )
    if out.get("status") == "invalid":
        raise HTTPException(status_code=400, detail=out.get("error") or "invalid")
    return out


@router.get("/ops-console/product/schema")
async def ops_console_product_schema_get_route(
    request: Request,
    tenant_id: Optional[str] = Query(None),
    object_type_id: Optional[str] = Query(None),
    x_aiplat_tenant_id: Optional[str] = Header(None, alias="X-AIPLAT-TENANT-ID"),
) -> Dict[str, Any]:
    """N24 产品面：读取 ObjectType schema。

    Args:
        request: FastAPI Request。
        tenant_id: 租户 query。
        object_type_id: 可选类型。
        x_aiplat_tenant_id: 租户 header。
    """
    from core.api.core_facade import get_knowledge_ops_console_schema

    tid = _tenant_from(request, x_aiplat_tenant_id, str(tenant_id or ""))
    if not tid:
        raise HTTPException(status_code=400, detail="tenant_id_required")
    out = get_knowledge_ops_console_schema(
        tenant_id=tid,
        object_type_id=str(object_type_id or ""),
    )
    if out.get("status") == "invalid":
        raise HTTPException(status_code=400, detail=out.get("error") or "invalid")
    return out


@router.put("/ops-console/product/schema")
async def ops_console_product_schema_put_route(
    request: Request,
    body: OpsConsoleSchemaSaveBody,
    x_aiplat_tenant_id: Optional[str] = Header(None, alias="X-AIPLAT-TENANT-ID"),
) -> Dict[str, Any]:
    """N24 产品面：保存 ObjectType schema 为 draft。

    Args:
        request: FastAPI Request。
        body: schema 保存体。
        x_aiplat_tenant_id: 租户 header。
    """
    from core.api.core_facade import save_knowledge_ops_console_schema

    tid = _tenant_from(request, x_aiplat_tenant_id, str(body.tenant_id or ""))
    if not tid:
        raise HTTPException(status_code=400, detail="tenant_id_required")
    out = save_knowledge_ops_console_schema(
        tenant_id=tid,
        object_type_id=str(body.object_type_id or ""),
        definition=dict(body.definition or {}),
        actor=str(body.actor or "ops-console-product"),
        reason=str(body.reason or "ops console schema editor save"),
        version=str(body.version or ""),
    )
    if out.get("status") == "invalid":
        raise HTTPException(status_code=400, detail=out.get("error") or "invalid")
    return out


@router.post("/ops-console/product/export")
async def ops_console_product_export_route(
    request: Request,
    body: OpsConsoleExportBody,
    x_aiplat_tenant_id: Optional[str] = Header(None, alias="X-AIPLAT-TENANT-ID"),
) -> Dict[str, Any]:
    """N24 产品面：浏览器可下载 JSON 导出（certified 恒假）。

    Args:
        request: FastAPI Request。
        body: 导出参数。
        x_aiplat_tenant_id: 租户 header。
    """
    from core.api.core_facade import export_knowledge_ops_console_product

    tid = _tenant_from(request, x_aiplat_tenant_id, str(body.tenant_id or ""))
    if not tid:
        raise HTTPException(status_code=400, detail="tenant_id_required")
    out = export_knowledge_ops_console_product(
        tid,
        domain_id=str(body.domain_id or ""),
        window_hours=int(body.window_hours),
        include_live=bool(body.include_live),
        output_root=body.output_root,
        write=bool(body.write),
    )
    if out.get("status") == "invalid":
        raise HTTPException(status_code=400, detail=out.get("error") or "invalid")
    if out.get("status") == "denied":
        raise HTTPException(status_code=403, detail=out.get("reason") or "denied")
    return out


@router.post("/ops-console/product/suite")
async def ops_console_product_suite_route() -> Dict[str, Any]:
    """N24 产品面：运维台套件。"""
    from core.api.core_facade import run_knowledge_ops_console_product_suite

    return run_knowledge_ops_console_product_suite()


@router.post("/ops-console/product/gate")
async def ops_console_product_gate_route(
    body: Optional[OpsConsoleGateBody] = None,
) -> Dict[str, Any]:
    """N24 产品面：运维台门槛门。

    Args:
        body: 可选已跑 suite 回执。
    """
    from core.api.core_facade import evaluate_knowledge_ops_console_product_gate

    suite = body.suite if body else None
    return evaluate_knowledge_ops_console_product_gate(suite)
