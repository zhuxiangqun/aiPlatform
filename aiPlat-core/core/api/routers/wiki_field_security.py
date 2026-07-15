"""
Field-Level Security API (cell/field-level access control).

Endpoints for managing field-level permission rules including
visibility constraints and redaction strategies per entity field.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Body, Query
from pydantic import BaseModel

router = APIRouter(tags=["wiki-field-security"])


class FieldPermissionRequest(BaseModel):
    entity_uri: str
    field_name: str
    visibility: str = "all"
    redaction_strategy: str = "mask"


@router.get("/field-permissions/{entity_uri:path}", response_model=Dict[str, Any])
async def get_field_permissions(entity_uri: str, collection: str = "default"):
    u"""Get field-level permission rules for an entity."""
    from core.policy.field_level_security import load_field_permissions
    perms = load_field_permissions(collection_id=collection)
    applicable = [p.to_dict() for p in perms if p.entity_uri == entity_uri]
    return {"entity_uri": entity_uri, "permissions": applicable, "total": len(applicable)}


@router.put("/field-permissions", response_model=Dict[str, Any])
async def set_field_permission_endpoint(req: FieldPermissionRequest, collection: str = "default"):
    u"""Set a field-level permission rule (visibility + redaction strategy)."""
    from core.policy.field_level_security import set_field_permission
    perm = set_field_permission(
        entity_uri=req.entity_uri,
        field_name=req.field_name,
        visibility=req.visibility,
        redaction_strategy=req.redaction_strategy,
        collection_id=collection,
    )
    return {"status": "ok", "permission": perm.to_dict()}


@router.delete("/field-permissions", response_model=Dict[str, Any])
async def remove_field_permission_endpoint(
    entity_uri: str = Body(...),
    field_name: str = Body(default=""),
    collection: str = "default",
):
    u"""Remove field-level permission(s). Pass empty field_name to clear all for entity."""
    from core.policy.field_level_security import remove_field_permission
    ok = remove_field_permission(entity_uri, field_name, collection_id=collection)
    return {"status": "ok" if ok else "not_found"}
