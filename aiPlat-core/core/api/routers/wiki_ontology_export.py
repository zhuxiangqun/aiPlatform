"""
Wiki Ontology Export API — OWL/RDF export and inference engine.
"""

from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["wiki-ontology-export"])

# ── OWL/RDF Export (Phase 5) ─────────────────────────────────────

@router.get("/export", response_model=Dict[str, Any])
async def export_ontology_rdf(format: str = "turtle", collection: str = "default"):
    """Export T-Box + A-Box as OWL/RDF.

    Supported formats: turtle (default), rdfxml, ntriples.
    Compatible with Protégé, GraphDB, Stardog, and other semantic web tools.
    """
    try:
        from core.harness.knowledge.knowledge_abox_builder import build_abox
        from core.harness.knowledge.knowledge_ontology import export_to_owl_rdf

        build_abox(collection_id=collection)
        rdf_text = export_to_owl_rdf(format=format)

        content_types = {
            "turtle": "text/turtle",
            "rdfxml": "application/rdf+xml",
            "ntriples": "application/n-triples",
        }
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(rdf_text, media_type=content_types.get(format, "text/plain"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")


@router.get("/infer", response_model=Dict[str, Any])
async def run_inference_engine(collection: str = "default"):
    """Run full inference engine and return suggested edges."""
    try:
        from core.harness.knowledge.knowledge_abox_builder import build_abox
        from core.harness.knowledge.knowledge_validator import TripleStore  # P0-A2 修复: 恢复原模块(定义处)
        from core.harness.knowledge.knowledge_validator import run_full_inference  # P0-A2 修复: 恢复原模块(定义处)
        from core.harness.knowledge.knowledge_validator import _short  # P0-A2 修复: 恢复原模块(定义处)
        onto = build_abox(collection_id=collection)
        store = TripleStore(onto.triples)
        inference = run_full_inference(store)

        suggestions = []
        for kind in ("transitive", "source_chain"):
            for inf in inference.get(kind, []):
                suggestions.append({
                    "kind": kind,
                    "from": _short(inf["subject"]),
                    "relation": inf["predicate"].replace("http://aiplat.local/knowledge#", ""),
                    "to": _short(inf["object"]),
                })

        return {
            "summary": inference.get("summary", ""),
            "suggestions": suggestions,
            "total": len(suggestions),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference failed: {e}")
