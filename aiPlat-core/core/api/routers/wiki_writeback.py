"""
WriteBack API (Phase 5 — external system integration).

Endpoints for registering, listing, and removing writeback targets
that push ontology changes to external systems on trigger actions.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Body, Query
from pydantic import BaseModel

router = APIRouter(tags=["wiki-writeback"])


class WritebackRegisterRequest(BaseModel):
    target_type: str = "rest_webhook"
    target_endpoint: str
    trigger_actions: List[str] = ["create", "update"]
    field_mapping: Dict[str, str] = {}
    auth: Dict[str, str] = {}


@router.get("/writebacks", response_model=Dict[str, Any])
async def list_writebacks(collection: str = "default"):
    u"""List all registered writeback configurations."""
    from core.harness.knowledge.knowledge_writeback import load_writebacks
    configs = load_writebacks(collection_id=collection)
    return {"writebacks": [c.to_dict() for c in configs], "total": len(configs)}


@router.post("/writebacks", response_model=Dict[str, Any])
async def register_writeback_endpoint(req: WritebackRegisterRequest, collection: str = "default"):
    u"""Register a new writeback target."""
    from core.harness.knowledge.knowledge_writeback import (
        register_writeback, WriteBackConfig, WriteBackTarget,
    )
    try:
        target = WriteBackTarget(req.target_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid target_type: {req.target_type}")

    config = WriteBackConfig(
        target_type=target,
        target_endpoint=req.target_endpoint,
        trigger_actions=req.trigger_actions,
        field_mapping=req.field_mapping,
        auth=req.auth,
    )
    register_writeback(config, collection_id=collection)
    return {"status": "ok", "config": config.to_dict()}


@router.delete("/writebacks", response_model=Dict[str, Any])
async def unregister_writeback_endpoint(target_endpoint: str, collection: str = "default"):
    u"""Remove a writeback target."""
    from core.harness.knowledge.knowledge_writeback import unregister_writeback
    ok = unregister_writeback(target_endpoint, collection_id=collection)
    return {"status": "ok" if ok else "not_found"}
