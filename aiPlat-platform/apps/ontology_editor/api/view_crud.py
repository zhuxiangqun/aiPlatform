"""Ontology Editor — Role View CRUD endpoints (v2.6)."""
from fastapi import APIRouter, HTTPException, Request
from typing import Any, Dict

# 为什么：走 apps.common_schemas，避免 `from api.*` 触发 api/__init__→routes→本模块环依赖
from apps.common_schemas import StatusResponse
from auth.request_identity import resolve_request_tenant

router = APIRouter(tags=["ontology-editor-views"])


def _cf():
    """Lazy-import CoreFacade functions."""
    from core.api.core_facade import (
        list_views_for_domain, get_view_for_domain, upsert_view_for_domain,
        delete_view_for_domain, resolve_term_in_view,
        get_ontology_domain_schema, validate_views_for_domain,
    )
    return (list_views_for_domain, get_view_for_domain, upsert_view_for_domain,
            delete_view_for_domain, resolve_term_in_view,
            get_ontology_domain_schema, validate_views_for_domain)


@router.get("/domains/{domain_id}/views", response_model=StatusResponse)
async def list_views(domain_id: str):
    """List all role-based views for a domain.

    Args:
        domain_id: domain 标识。
    """
    try:
        (list_views_for_domain, *_) = _cf()
        views = list_views_for_domain(domain_id)
        return {"domain_id": domain_id, "views": views, "total": len(views)}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list views: {e}")


@router.get("/domains/{domain_id}/views/{role}", response_model=StatusResponse)
async def get_view(domain_id: str, role: str):
    """Get a single role view definition.

    Args:
        domain_id: domain 标识。
        role: role 参数。
    """
    try:
        (_, get_view_for_domain, *_) = _cf()
        view = get_view_for_domain(domain_id, role)
        return {"domain_id": domain_id, "role": role, "view": view}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except LookupError:
        raise HTTPException(status_code=404, detail=f"View not found for role: {role}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get view: {e}")


@router.post("/domains/{domain_id}/views/validate", response_model=StatusResponse)
async def validate_views(domain_id: str):
    """Validate all role views for a domain.

    Args:
        domain_id: domain 标识。
    """
    try:
        (*_, validate_views_for_domain) = _cf()
        return validate_views_for_domain(domain_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {e}")


@router.post("/domains/{domain_id}/views", response_model=StatusResponse)
async def upsert_view(domain_id: str, data: Dict[str, Any], request: Request):
    """Create or update a role view in a domain YAML.

    Args:
        domain_id: domain 标识。
        data: data 参数。
        request: FastAPI Request（经身份解析取 tenant）。
    """
    try:
        role = data.get("role") or data.get("name", "")
        view_data = data.get("view") or data.get("data", {})
        if not role:
            raise HTTPException(status_code=400, detail="role is required")
        if not view_data:
            view_data = {k: v for k, v in data.items() if k not in ("role", "name")}
        (_, _, upsert_view_for_domain, *_) = _cf()
        # 为什么：N09 K10 — view 写后清租户 GraphIndex 缓存
        tenant_id = resolve_request_tenant(request)
        result = upsert_view_for_domain(
            domain_id, role, view_data, tenant_id=tenant_id
        )
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upsert view: {e}")


@router.delete("/domains/{domain_id}/views/{role}", response_model=StatusResponse)
async def delete_view(domain_id: str, role: str, request: Request):
    """Delete a role view from a domain YAML.

    Args:
        domain_id: domain 标识。
        role: role 参数。
        request: FastAPI Request（经身份解析取 tenant）。
    """
    try:
        (_, _, _, delete_view_for_domain, *_) = _cf()
        # 为什么：N09 K10 — view 删除后清租户 GraphIndex 缓存
        tenant_id = resolve_request_tenant(request)
        result = delete_view_for_domain(domain_id, role, tenant_id=tenant_id)
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete view: {e}")


@router.get("/domains/{domain_id}/views/{role}/resolve-term", response_model=StatusResponse)
async def resolve_term(domain_id: str, role: str, term: str = ""):
    """Resolve a term's meaning for a specific role's perspective.

    Args:
        domain_id: domain 标识。
        role: role 参数。
        term: term 参数。
    """
    if not term:
        raise HTTPException(status_code=400, detail="term query parameter required")
    try:
        (_, _, _, _, resolve_term_in_view, *_) = _cf()
        result = resolve_term_in_view(domain_id, role, term)
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Term resolution failed: {e}")
