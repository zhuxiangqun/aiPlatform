"""
Scene Model API (Phase A — purpose-driven pipeline templates)
and Growth Metrics API (Phase E — knowledge compound interest).

Scene endpoints: CRUD for ontology scene templates with instantiation.
Growth endpoints: knowledge base growth statistics and snapshots.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Body, Query
from pydantic import BaseModel

router = APIRouter(tags=["wiki-scenes"])


# ── Scene Model ─────────────────────────────────────────────────

class SceneCreateRequest(BaseModel):
    scene_id: str
    name: str = ""
    description: str = ""
    required_entities: List[str] = []
    algorithm_nodes: List[Dict[str, Any]] = []
    llm_judgment_nodes: List[Dict[str, Any]] = []
    entry_conditions: Dict[str, Any] = {}
    expected_outcomes: List[Dict[str, Any]] = []
    tags: List[str] = []


@router.get("/scenes", response_model=Dict[str, Any])
async def list_scene_models(collection: str = "default"):
    u"""List all ontology scene templates. Auto-seeds built-in scenes on first access."""
    from core.harness.knowledge.scene_model import list_scenes, create_builtin_scenes
    scenes = list_scenes(collection_id=collection)
    if not scenes:
        from core.harness.knowledge.scene_model import save_scene
        builtins = create_builtin_scenes()
        for s in builtins:
            save_scene(s, collection_id=collection)
        scenes = list_scenes(collection_id=collection)
    return {"scenes": [s.to_dict() for s in scenes], "total": len(scenes)}


@router.post("/scenes", response_model=Dict[str, Any])
async def create_scene_model(req: SceneCreateRequest, collection: str = "default"):
    from core.harness.knowledge.scene_model import OntologyScene, save_scene
    scene = OntologyScene(
        scene_id=req.scene_id, name=req.name, description=req.description,
        required_entities=req.required_entities, algorithm_nodes=req.algorithm_nodes,
        llm_judgment_nodes=req.llm_judgment_nodes, entry_conditions=req.entry_conditions,
        expected_outcomes=req.expected_outcomes, tags=req.tags,
    )
    save_scene(scene, collection_id=collection)
    return {"status": "ok", "scene": scene.to_dict()}


@router.get("/scenes/{scene_id}", response_model=Dict[str, Any])
async def get_scene_model(scene_id: str, collection: str = "default"):
    from core.harness.knowledge.scene_model import get_scene
    scene = get_scene(scene_id, collection_id=collection)
    if not scene:
        raise HTTPException(status_code=404, detail=f"Scene '{scene_id}' not found")
    return {"scene": scene.to_dict(), "pipeline_stages": scene.to_pipeline_stages(),
            "stage_count": len(scene.to_pipeline_stages())}


@router.post("/scenes/{scene_id}/instantiate", response_model=Dict[str, Any])
async def instantiate_scene_model(scene_id: str, params: Dict[str, Any] = Body(default={}), collection: str = "default"):
    from core.harness.knowledge.scene_model import instantiate_scene
    config = instantiate_scene(scene_id, params=params, collection_id=collection)
    if not config:
        raise HTTPException(status_code=404, detail=f"Scene '{scene_id}' not found")
    return {"pipeline_config": config, "stage_count": len(config.get("stages", []))}


@router.delete("/scenes/{scene_id}", response_model=Dict[str, Any])
async def delete_scene_model(scene_id: str, collection: str = "default"):
    from core.harness.knowledge.scene_model import delete_scene
    ok = delete_scene(scene_id, collection_id=collection)
    return {"status": "ok" if ok else "not_found"}


# ── Growth Metrics ──────────────────────────────────────────────

@router.get("/growth-stats", response_model=Dict[str, Any])
async def get_growth_stats(days: int = 30, collection: str = "default"):
    u"""Get knowledge base growth statistics for the last N days."""
    from core.harness.knowledge.knowledge_growth import get_growth_stats, estimate_compound_value
    stats = get_growth_stats(collection_id=collection, days=days)
    compound = estimate_compound_value(collection_id=collection)
    return {**stats, "compound": compound}


@router.post("/growth/snapshot", response_model=Dict[str, Any])
async def take_snapshot(collection: str = "default"):
    u"""Manually trigger a growth snapshot."""
    from core.harness.knowledge.knowledge_growth import take_growth_snapshot
    snap = take_growth_snapshot(collection_id=collection)
    return {"status": "ok", "snapshot": snap.to_dict()}
