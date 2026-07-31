from api.schemas_response import StatusResponse
u"""Ontology Editor — Scoring Models API endpoints (v2.7)."""
from fastapi import APIRouter, HTTPException, Query
from typing import Any, Dict, List, Optional

router = APIRouter(tags=["ontology-editor-scoring"])


@router.get("/domains/{domain_id}/scoring-models", response_model=StatusResponse)
async def list_scoring_models(domain_id: str):
    u"""List all scoring models for a domain."""
    try:
        from core.api.core_facade import get_ontology_domain_schema
        schema = get_ontology_domain_schema(domain_id)
        from core.harness.knowledge.scoring_engine import load_models
        models = load_models(schema)
        return {
            "domain_id": domain_id,
            "models": [{"name": m.name, "label": m.label, "binds_to": m.binds_to,
                         "rule_count": len(m.rules)} for m in models],
            "total": len(models),
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/domains/{domain_id}/scoring-models/{model_name}/evaluate", response_model=StatusResponse)
async def evaluate_entity(domain_id: str, model_name: str, entity: str = Query("")):
    u"""Evaluate a single entity against a scoring model."""
    if not entity:
        raise HTTPException(status_code=400, detail="entity query parameter required")
    try:
        from core.api.core_facade import get_ontology_domain_schema
        schema = get_ontology_domain_schema(domain_id)
        from core.harness.knowledge.scoring_engine import load_models, evaluate
        models = {m.name: m for m in load_models(schema)}
        model = models.get(model_name)
        if not model:
            raise HTTPException(status_code=404, detail=f"Scoring model not found: {model_name}")
        result = evaluate(entity, model, domain_id)
        return {
            "domain_id": domain_id, "model": model_name, "entity": entity,
            "total_score": result.total_score, "level": result.level,
            "action": result.action, "rule_scores": result.rule_scores,
            "details": result.details,
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/domains/{domain_id}/scoring-models/{model_name}/evaluate-batch", response_model=StatusResponse)
async def evaluate_batch(domain_id: str, model_name: str, data: Dict[str, Any]):
    u"""Batch evaluate all entities of a class against a scoring model."""
    try:
        class_name = data.get("class_name", "")
        if not class_name:
            raise HTTPException(status_code=400, detail="class_name is required")
        from core.api.core_facade import get_ontology_domain_schema
        schema = get_ontology_domain_schema(domain_id)
        from core.harness.knowledge.scoring_engine import load_models, evaluate_batch
        models = {m.name: m for m in load_models(schema)}
        model = models.get(model_name)
        if not model:
            raise HTTPException(status_code=404, detail=f"Scoring model not found: {model_name}")
        results = evaluate_batch(class_name, model, domain_id)
        return {
            "domain_id": domain_id, "model": model_name, "class": class_name,
            "results": [{"entity": r.entity_name, "score": r.total_score,
                          "level": r.level, "action": r.action} for r in results],
            "total_evaluated": len(results),
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/domains/{domain_id}/scoring-models/{model_name}/alerts", response_model=StatusResponse)
async def get_alerts(domain_id: str, model_name: str):
    u"""Get all high/medium level alerts for a scoring model."""
    try:
        from core.api.core_facade import get_ontology_domain_schema
        schema = get_ontology_domain_schema(domain_id)
        from core.harness.knowledge.scoring_engine import load_models, get_alerts
        models = {m.name: m for m in load_models(schema)}
        model = models.get(model_name)
        if not model:
            raise HTTPException(status_code=404, detail=f"Scoring model not found: {model_name}")
        alerts = get_alerts(model, domain_id)
        return {
            "domain_id": domain_id, "model": model_name,
            "alerts": [{"entity": r.entity_name, "score": r.total_score,
                         "level": r.level, "action": r.action} for r in alerts],
            "total": len(alerts),
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Domain not found: {domain_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
