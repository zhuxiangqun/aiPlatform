"""
Semantic Suggestions API (Phase 3 — LLM-driven evolution).

Endpoints for generating and evaluating ontology evolution suggestions
via LLM-driven semantic analysis (merge detection, field gap analysis,
relation inference).
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Body, Query
from pydantic import BaseModel

router = APIRouter(tags=["wiki-semantic-suggestions"])


class SemanticSuggestRequest(BaseModel):
    collection: str = "default"
    max_suggestions: int = 5
    confidence_threshold: float = 0.7
    include_llm: bool = True


@router.post("/suggestions/semantic", response_model=Dict[str, Any])
async def generate_semantic_suggestions_endpoint(req: SemanticSuggestRequest = Body(default=None)):
    u"""Generate semantic ontology evolution suggestions via LLM (Tier 2).

    Dimensions: semantic merge detection, field gap analysis, relation inference.
    Set include_llm=False to get only Tier 1 (rule-based) suggestions.
    """
    if req is None:
        req = SemanticSuggestRequest()

    if not req.include_llm:
        from core.harness.knowledge.knowledge_ontology import add_suggestions_from_patterns
        suggestions = add_suggestions_from_patterns(
            collection_id=req.collection,
        )
        return {"suggestions": suggestions, "total": len(suggestions), "source": "rule"}

    try:
        from core.harness.knowledge.knowledge_evolution_llm import generate_semantic_suggestions
        suggestions = await generate_semantic_suggestions(
            collection_id=req.collection,
            max_suggestions=req.max_suggestions,
            confidence_threshold=req.confidence_threshold,
        )
        return {"suggestions": suggestions, "total": len(suggestions), "source": "llm"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Semantic suggestion generation failed: {e}")


@router.post("/suggestions/{suggestion_id}/impact", response_model=Dict[str, Any])
async def predict_suggestion_impact(suggestion_id: str, collection: str = "default"):
    u"""Predict the impact scope of accepting an evolution suggestion."""
    from core.harness.knowledge.knowledge_ontology import (
        load_pending_suggestions, get_ontology,
    )
    from core.harness.knowledge.knowledge_evolution_llm import predict_evolution_impact

    suggestions = load_pending_suggestions(collection)
    suggestion = next((s for s in suggestions if s.get("id") == suggestion_id), None)
    if not suggestion:
        raise HTTPException(status_code=404, detail=f"Suggestion '{suggestion_id}' not found")

    onto = get_ontology()
    impact = predict_evolution_impact(suggestion, onto)
    return impact
