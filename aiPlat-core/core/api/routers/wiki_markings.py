"""
Wiki Markings API — ontology entity markings and permissions endpoints.
Extracted from wiki.py:5240-5349 (Markings API section).
Parent router should include_router with prefix="/ontology".
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["wiki-markings"])


# ══════════════════════════════════════════════════════════════
# Request Models
# ══════════════════════════════════════════════════════════════

class MarkingSetRequest(BaseModel):
    entity_uri: str
    label: str
    level: int = 2  # 1=public, 2=internal, 3=confidential, 4=restricted
    scope: str = ""


class MarkingDeleteRequest(BaseModel):
    entity_uri: str
    label: str = ""


# ══════════════════════════════════════════════════════════════
# Markings Endpoints
# ══════════════════════════════════════════════════════════════

@router.put("/markings", response_model=Dict[str, Any])
async def set_entity_marking(req: MarkingSetRequest, collection: str = "default"):
    u"""Set a marking on an ontology entity."""
    from core.harness.knowledge.knowledge_markings import set_marking, MarkingLevel
    try:
        level = MarkingLevel(max(1, min(4, req.level)))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid level: {req.level}")

    marking = set_marking(
        entity_uri=req.entity_uri,
        label=req.label,
        level=level,
        scope=req.scope,
        collection_id=collection,
    )
    return {"status": "ok", "marking": marking.to_dict()}


@router.delete("/markings", response_model=Dict[str, Any])
async def remove_entity_marking(req: MarkingDeleteRequest, collection: str = "default"):
    u"""Remove a marking from an entity (or all if label is empty)."""
    from core.harness.knowledge.knowledge_markings import remove_marking
    ok = remove_marking(
        entity_uri=req.entity_uri,
        label=req.label,
        collection_id=collection,
    )
    return {"status": "ok" if ok else "not_found", "removed": ok}


@router.get("/markings/{entity_uri:path}", response_model=Dict[str, Any])
async def get_entity_marking_info(
    entity_uri: str,
    collection: str = "default",
    resolve_effective: bool = True,
):
    u"""Get explicit + effective markings for an entity, with propagation traces."""
    from core.harness.knowledge.knowledge_markings import (
        get_entity_markings, get_propagation_tree,
    )
    if resolve_effective:
        result = get_propagation_tree(entity_uri, collection_id=collection)
    else:
        result = get_entity_markings(entity_uri, collection_id=collection, resolve_effective=False)
    return result


# ══════════════════════════════════════════════════════════════
# Permissions Endpoints
# ══════════════════════════════════════════════════════════════

@router.put("/permissions", response_model=Dict[str, Any])
async def grant_entity_permission(
    entity_uri: str = Body(...),
    role: str = Body(...),
    actions: List[str] = Body(...),
    collection: str = "default",
):
    u"""Grant per-object permission on an ontology entity."""
    from core.policy.object_permission import grant_object_permission
    perm = grant_object_permission(
        entity_uri=entity_uri,
        role=role,
        actions=actions,
        collection_id=collection,
    )
    return {"status": "ok", "permission": perm.to_dict()}


@router.delete("/permissions", response_model=Dict[str, Any])
async def revoke_entity_permission(
    entity_uri: str = Body(...),
    role: str = Body(default=""),
    action: str = Body(default=""),
    collection: str = "default",
):
    u"""Revoke a per-object permission."""
    from core.policy.object_permission import revoke_object_permission
    ok = revoke_object_permission(
        entity_uri=entity_uri,
        role=role,
        action=action,
        collection_id=collection,
    )
    return {"status": "ok" if ok else "not_found", "revoked": ok}


@router.get("/permissions/{entity_uri:path}", response_model=Dict[str, Any])
async def list_entity_permissions(
    entity_uri: str,
    collection: str = "default",
):
    u"""List all effective permissions for an ontology entity."""
    from core.policy.object_permission import get_effective_permissions
    perms = get_effective_permissions(entity_uri, collection_id=collection)
    return {"entity_uri": entity_uri, "permissions": perms}
