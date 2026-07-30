"""
Knowledge extraction REST API — document upload → LLM extract → drafts → confirm.
Mounted at /api/platform/apps/fde/extract
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form

from core.harness.knowledge_pipeline.extractor import (
    ExtractionPipeline,
    PendingExtractionStore,
    ExtractionResult,
)

router = APIRouter(tags=["fde-extraction"])

logger = logging.getLogger(__name__)
_store = PendingExtractionStore()


@router.post("/extract")
async def extract_document(
    text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    domain_id: str = Form("default"),
    doc_name: str = Form("uploaded_doc"),
):
    """Extract entities + relations from text or uploaded file.

    Accepts either raw text or a file upload (PDF/Word/text).
    Returns extraction results with confidence routing.
    """
    content = text or ""
    if file:
        try:
            raw = await file.read()
            content = raw.decode("utf-8", errors="replace")
            doc_name = doc_name or file.filename or "uploaded_doc"
        except Exception as e:
            logger.warning("File read failed: %s", e)
            try:
                content = raw.decode("latin-1", errors="replace")
            except Exception:
                raise HTTPException(status_code=400, detail="Unable to read file content")

    if not content.strip():
        raise HTTPException(status_code=400, detail="No text content provided")

    pipeline = ExtractionPipeline()
    results = await pipeline.run(content, doc_name=doc_name, domain_id=domain_id)

    # Persist pending extractions
    await _store.initialize()
    for r in results:
        await _store.save(r)

    # Return frontend-friendly summary
    return {
        "extractions": [
            {
                "extraction_id": r.extraction_id,
                "domain_id": r.domain_id,
                "source_doc": r.source_doc,
                "overall_confidence": r.overall_confidence,
                "entity_count": len(r.entities),
                "relation_count": len(r.relations),
                "status": r.status,
                "draft_yaml_path": r.draft_yaml_path,
                "top_entities": [
                    {"name": e.name, "class_type": e.class_type, "confidence": e.confidence}
                    for e in r.entities[:10]
                ],
            }
            for r in results
        ],
        "count": len(results),
    }


@router.get("/extractions/pending")
async def list_pending_extractions(
    domain_id: str = Query("", description="Filter by domain"),
):
    """List pending extractions awaiting review."""
    await _store.initialize()
    items = await _store.list_pending(domain_id=domain_id)
    return {"pending": items, "count": len(items)}


@router.post("/extractions/{extraction_id}/confirm")
async def confirm_extraction(extraction_id: str):
    """Confirm an extraction → merge into formal ontology."""
    await _store.initialize()
    ok = await _store.confirm(extraction_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Extraction not found or already resolved")
    return {"status": "confirmed", "extraction_id": extraction_id}


@router.post("/extractions/{extraction_id}/reject")
async def reject_extraction(extraction_id: str):
    """Reject an extraction → mark as discarded."""
    await _store.initialize()
    ok = await _store.reject(extraction_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Extraction not found or already resolved")
    return {"status": "rejected", "extraction_id": extraction_id}


# ═══════════════════════════════════════════════════════════
# Cross-domain resolution
# ═══════════════════════════════════════════════════════════

@router.get("/resolution/candidates")
async def list_resolution_candidates(
    view_name: str = Query("unified_customer", description="Cross-domain view name"),
):
    """List cross-domain merge candidates from registry.json views."""
    try:
        from core.harness.knowledge_pipeline.resolver import CrossDomainResolver
        resolver = CrossDomainResolver()
        candidates = resolver.find_candidates(view_name)
        return {
            "view": view_name,
            "candidates": [
                {
                    "left": c.left,
                    "right": c.right,
                    "score": c.score,
                    "strategy": c.strategy,
                    "evidence": c.evidence,
                }
                for c in candidates[:50]
            ],
            "count": len(candidates),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/resolution/resolve")
async def resolve_cross_domain(body: Dict[str, Any]):
    """Create a cross-domain edge between two entities."""
    view_name = body.get("view_name", "unified_customer")
    left_id = str(body.get("left_id", ""))
    right_id = str(body.get("right_id", ""))
    left_domain = str(body.get("left_domain", ""))
    right_domain = str(body.get("right_domain", ""))
    confidence = float(body.get("confidence", 1.0))

    if not all([left_id, right_id, left_domain, right_domain]):
        raise HTTPException(status_code=400, detail="left_id, right_id, left_domain, right_domain required")

    try:
        from core.harness.knowledge_pipeline.resolver import CrossDomainResolver
        ok = CrossDomainResolver.resolve(view_name, left_id, right_id, left_domain, right_domain, confidence)
        return {"status": "resolved" if ok else "failed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/rag/context")
async def get_entity_context(body: Dict[str, Any]):
    """Pre-load GraphRAG context for an entity (used by ActionRegistry)."""
    entity_id = str(body.get("entity_id", ""))
    domain_id = str(body.get("domain_id", "default"))
    action_context = str(body.get("context", ""))

    if not entity_id:
        raise HTTPException(status_code=400, detail="entity_id required")

    try:
        from core.harness.knowledge_pipeline.retriever import GraphRAGRetriever
        retriever = GraphRAGRetriever()
        context = await retriever.get_entity_context(entity_id, domain_id, action_context)
        return context
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])


# ═══════════════════════════════════════════════════════════
# Decision throttle check (frontend pre-flight)
# ═══════════════════════════════════════════════════════════

@router.post("/throttle/check")
async def check_throttle_status(body: Dict[str, Any]):
    """Pre-flight throttle check before executing an action."""
    action_id = str(body.get("action_id", ""))
    actor = str(body.get("actor", "system"))
    domain_id = str(body.get("domain_id", "fde-delivery"))

    if not action_id:
        raise HTTPException(status_code=400, detail="action_id required")

    try:
        from core.harness.infrastructure.throttle import DecisionThrottle
        from core.harness.ontology_engine.action_registry import get_action_registry
        reg = get_action_registry()
        c = reg.get(action_id)
        if not c:
            raise HTTPException(status_code=404, detail="Action not found")

        throttle = DecisionThrottle()
        tl = getattr(c, 'throttle_limit', 0) or 0
        result = await throttle.check_rate_limit(
            actor=actor, action_id=action_id, domain_id=domain_id or c.domain_id,
            time_window_sec=getattr(c, 'throttle_window_seconds', 3600) or 3600,
            limit=tl, block_on_breach=False,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])


# ═══════════════════════════════════════════════════════════
# Ontology evolution (Phase 3)
# ═══════════════════════════════════════════════════════════

@router.post("/ontology/proposals")
async def create_ontology_proposal(body: Dict[str, Any]):
    """Submit an ontology evolution proposal (add/split/merge/deprecate)."""
    domain_id = str(body.get("domain_id", "fde-delivery"))
    changes = body.get("changes", {})
    author = str(body.get("author", "system"))

    if not changes:
        raise HTTPException(status_code=400, detail="changes required")

    try:
        from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore
        store = VersionedOntologyStore(domain_id)
        proposal_id = await store.create_proposal(changes, author)
        return {"status": "draft", "proposal_id": proposal_id, "domain_id": domain_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/ontology/proposals")
async def list_ontology_proposals(
    domain_id: str = Query("", description="Filter by domain"),
):
    """List ontology evolution proposals."""
    try:
        from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore
        store = VersionedOntologyStore(domain_id or "fde-delivery")
        proposals = await store.list_proposals(domain_id=domain_id)
        return {"proposals": proposals, "count": len(proposals)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/ontology/proposals/{proposal_id}/apply")
async def apply_ontology_proposal(proposal_id: str):
    """Apply an approved ontology proposal."""
    try:
        from core.harness.infrastructure.action_store import ActionStore
        store = ActionStore()
        await store.initialize()
        proposal = await store.get_ontology_proposal(proposal_id)
        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")

        domain_id = proposal.get("domain_id", "fde-delivery")
        from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore
        vstore = VersionedOntologyStore(domain_id)
        ok = await vstore.apply_proposal(proposal_id)
        return {"status": "applied" if ok else "failed", "proposal_id": proposal_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])
