"""
Wiki Evidence Chain API — full evidence trace for a Wiki claim/atom.
"""

from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["wiki-evidence"])

# ── Evidence Chain API (Phase 4) ──────────────────────────────────

@router.get("/claim/{title}/evidence-chain", response_model=Dict[str, Any])
async def get_claim_evidence_chain(title: str, collection: str = "default"):
    """Return full evidence chain for a Wiki claim/atom.

    Chain: page → source documents → contradictions → resolutions.
    """
    try:
        from core.api.core_facade import read_page, search_pages  # P0-A2: 经 CoreFacade
        from core.harness.knowledge.knowledge_abox_builder import build_abox
        from core.harness.knowledge.knowledge_validator import TripleStore, _short

        page = read_page(title, collection_id=collection)
        if not page:
            raise HTTPException(status_code=404, detail=f"Page '{title}' not found")

        # 1. Direct source evidence
        source_articles = page.get("source_articles", [])
        evidence_text = None
        # Check if this is an atom page with evidence_text in frontmatter
        fm = page.get("fm", {})
        if fm.get("source_doc_id"):
            evidence_text = fm.get("evidence_text", "")
            source_articles = [fm["source_doc_id"]]
        # Fallback: evidence_text may be in summary field (write_atom stores it there)
        if not evidence_text:
            evidence_text = fm.get("evidence_text") or page.get("summary", "") or None
        # Parse evidence metadata from body HTML comments
        body = page.get("body", "")
        evidence_meta = {}
        import re as _re
        for m in _re.finditer(r'<!--\s*(source_doc_id|evidence_start|evidence_end|confidence):\s*([\d.]+[^\s-]*)\s*-->', body):
            key, val = m.group(1), m.group(2)
            try:
                evidence_meta[key] = float(val) if key in ("confidence", "evidence_start", "evidence_end") else val
            except ValueError:
                evidence_meta[key] = val
        if evidence_meta.get("source_doc_id") and not source_articles:
            source_articles = [evidence_meta["source_doc_id"]]

        # 2. Contradictions and related pages
        contradictions = page.get("contradictions", [])
        related = page.get("related", [])

        # 3. Ontology-level contradictions (from A-Box)
        onto = build_abox(collection_id=collection)
        store = TripleStore(onto.triples)
        onto_contradictions = [
            _short(c) for c in store.objects(f"http://aiplat.local/knowledge#{title}",
                                              "http://aiplat.local/knowledge#contradicts")
        ]

        # 4. Stale references
        stale = page.get("stale_references", [])

        return {
            "claim": title,
            "source_articles": source_articles,
            "evidence_text": evidence_text,
            "contradictions": contradictions,
            "onto_contradictions": [c for c in onto_contradictions if c != title],
            "related": related,
            "stale_references": stale,
            "has_controversy": len(contradictions) > 0 or len(onto_contradictions) > 1,
            "category": page.get("category", ""),
            "last_updated": page.get("last_updated", ""),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evidence chain failed: {e}")
