u"""Ontology Editor — Role View CRUD endpoints (v2.6)."""
from fastapi import APIRouter, HTTPException
from typing import Any, Dict

router = APIRouter(tags=["ontology-editor-views"])


@router.get("/domains/{domain_id}/views", response_model=Dict[str, Any])
async def list_views(domain_id: str):
    u"""List all role-based views for a domain."""
    try:
        from core.api.core_facade import get_ontology_domain_schema
        from core.harness.knowledge.role_view import load_views, list_roles
        schema = get_ontology_domain_schema(domain_id)
        compiled = load_views(schema)
        return {"domain_id": domain_id, "views": list_roles(compiled), "total": len(compiled)}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list views: {e}")


@router.get("/domains/{domain_id}/views/{role}", response_model=Dict[str, Any])
async def get_view(domain_id: str, role: str):
    u"""Get a single role view definition."""
    try:
        from core.api.core_facade import get_ontology_domain_schema
        from core.harness.knowledge.role_view import load_views
        schema = get_ontology_domain_schema(domain_id)
        compiled = load_views(schema)
        view = compiled.get(role)
        if not view:
            raise HTTPException(status_code=404, detail=f"View not found for role: {role}")
        return {"domain_id": domain_id, "role": role, "view": view}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get view: {e}")


@router.post("/domains/{domain_id}/views", response_model=Dict[str, Any])
async def upsert_view(domain_id: str, data: Dict[str, Any]):
    u"""Create or update a role view in a domain YAML."""
    try:
        role = data.get("role") or data.get("name", "")
        view_data = data.get("view") or data.get("data", {})
        if not role:
            raise HTTPException(status_code=400, detail="role is required")
        if not view_data:
            view_data = {k: v for k, v in data.items() if k not in ("role", "name")}

        from core.api.core_facade import get_ontology_domain_schema
        import yaml, os

        schema = get_ontology_domain_schema(domain_id)
        schema.setdefault("views", {})
        schema["views"][role] = view_data

        base_dir = os.path.expanduser(os.getenv("AIPLAT_ONTOLOGY_DIR", "~/.aiplat/ontologies"))
        file_path = f"{base_dir}/{domain_id}.yaml"

        with open(file_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        raw.setdefault("views", {})
        raw["views"][role] = view_data

        from core.harness.knowledge.yaml_serializer import dict_to_yaml
        open(file_path, "w", encoding="utf-8").write(dict_to_yaml(raw))

        return {"domain_id": domain_id, "role": role, "status": "upserted"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upsert view: {e}")


@router.delete("/domains/{domain_id}/views/{role}", response_model=Dict[str, Any])
async def delete_view(domain_id: str, role: str):
    u"""Delete a role view from a domain YAML."""
    try:
        import yaml, os
        base_dir = os.path.expanduser(os.getenv("AIPLAT_ONTOLOGY_DIR", "~/.aiplat/ontologies"))
        file_path = f"{base_dir}/{domain_id}.yaml"

        with open(file_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        raw.get("views", {}).pop(role, None)

        from core.harness.knowledge.yaml_serializer import dict_to_yaml
        open(file_path, "w", encoding="utf-8").write(dict_to_yaml(raw))

        return {"domain_id": domain_id, "role": role, "status": "deleted"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete view: {e}")


@router.post("/domains/{domain_id}/views/validate", response_model=Dict[str, Any])
async def validate_views(domain_id: str):
    u"""Validate all role views for a domain."""
    try:
        from core.api.core_facade import get_ontology_domain_schema
        from core.harness.knowledge.role_view import validate_views
        schema = get_ontology_domain_schema(domain_id)
        result = validate_views(schema)
        return {"domain_id": domain_id, **result}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {e}")


@router.get("/domains/{domain_id}/views/{role}/resolve-term", response_model=Dict[str, Any])
async def resolve_term(domain_id: str, role: str, term: str = ""):
    u"""Resolve a term's meaning for a specific role's perspective."""
    if not term:
        raise HTTPException(status_code=400, detail="term query parameter required")
    try:
        from core.api.core_facade import get_ontology_domain_schema
        from core.harness.knowledge.role_view import load_views, resolve_term as _resolve_term
        schema = get_ontology_domain_schema(domain_id)
        compiled = load_views(schema)
        definition = _resolve_term(term, role, compiled)
        if not definition:
            return {"domain_id": domain_id, "role": role, "term": term, "definition": None, "found": False}
        return {"domain_id": domain_id, "role": role, "term": term, "definition": definition, "found": True}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Term resolution failed: {e}")
