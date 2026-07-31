u"""Ontology Editor — Role View CRUD endpoints (v2.6)."""
from fastapi import APIRouter, HTTPException
from typing import Any, Dict

router = APIRouter(tags=["ontology-editor-views"])


def _cf():
    u"""Lazy-import CoreFacade functions."""
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
    u"""List all role-based views for a domain."""
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
    u"""Get a single role view definition."""
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
    u"""Validate all role views for a domain."""
    try:
        (*_, validate_views_for_domain) = _cf()
        return validate_views_for_domain(domain_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {e}")


@router.post("/domains/{domain_id}/views", response_model=StatusResponse)
async def upsert_view(domain_id: str, data: Dict[str, Any]):
    u"""Create or update a role view in a domain YAML."""
    try:
        role = data.get("role") or data.get("name", "")
        view_data = data.get("view") or data.get("data", {})
        if not role:
            raise HTTPException(status_code=400, detail="role is required")
        if not view_data:
            view_data = {k: v for k, v in data.items() if k not in ("role", "name")}
        (_, _, upsert_view_for_domain, *_) = _cf()
        result = upsert_view_for_domain(domain_id, role, view_data)
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upsert view: {e}")


@router.delete("/domains/{domain_id}/views/{role}", response_model=StatusResponse)
async def delete_view(domain_id: str, role: str):
    u"""Delete a role view from a domain YAML."""
    try:
        (_, _, _, delete_view_for_domain, *_) = _cf()
        result = delete_view_for_domain(domain_id, role)
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete view: {e}")


@router.get("/domains/{domain_id}/views/{role}/resolve-term", response_model=StatusResponse)
async def resolve_term(domain_id: str, role: str, term: str = ""):
    u"""Resolve a term's meaning for a specific role's perspective."""
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
