"""
Knowledge Ontology A-Box Builder.

Builds the A-Box (population / instance layer) from existing Wiki + KB data.
Called on startup, after ingest, and on-demand for rebuild.

Sources:
  1. ~/.aiplat/wiki/**/*.md → WikiPage instances + relations
  2. ~/.aiplat/wiki/index.json → metadata supplement
  3. ~/.aiplat/kb/tenants/*/kb.sqlite3 → KBDocument instances
"""

from __future__ import annotations

import json as _json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from core.harness.knowledge.knowledge_ontology import (
    AI, KnowledgeOntology, OntologyTriple,
    get_ontology, reset_ontology,
)

logger = logging.getLogger(__name__)


def _wiki_root(collection_id: str = "default") -> Path:
    """Get wiki root for a specific collection, delegating to wiki_engine."""
    from core.harness.knowledge.wiki_engine import _wiki_root as _engine_wiki_root
    return _engine_wiki_root(collection_id)


def build_abox(partial: Optional[str] = None, *, collection_id: str = "default") -> KnowledgeOntology:
    """
    Build A-Box from current Wiki + KB data.
    
    Args:
        partial: If set to a doc_id or page title, only rebuild that slice.
                 If None, full rebuild.
        collection_id: Wiki collection to build A-Box for.
    
    Returns the ontology with populated triples.
    """
    onto = get_ontology()
    start = time.time()
    
    if partial is None:
        onto.triples = []  # Full rebuild
    else:
        # Remove only triples related to this entity
        onto.triples = [t for t in onto.triples 
                        if partial not in (t.subject, t.object)]
    
    # ── Step 1: Load Wiki pages ──
    wiki_pages = _scan_wiki_pages(partial, collection_id=collection_id)
    _build_wiki_triples(onto, wiki_pages)
    
    # ── Step 2: Load KB documents ──
    kb_docs = _scan_kb_documents(partial)
    _build_kb_triples(onto, kb_docs)
    
    # ── Step 3: Validate cross-references ──
    _cross_validate_sources(onto, wiki_pages, kb_docs)
    
    logger.info(f"A-Box built: {len(onto.triples)} triples, {len(wiki_pages)} Wiki pages, "
                f"{len(kb_docs)} KB docs, {time.time() - start:.2f}s")
    
    return onto


# ══════════════════════════════════════════════════════════════
# Wiki Page Scanner
# ══════════════════════════════════════════════════════════════

def _scan_wiki_pages(partial: Optional[str] = None, *, collection_id: str = "default") -> List[Dict[str, Any]]:
    """Scan wiki collection for all .md files, parse frontmatter."""
    root = _wiki_root(collection_id)
    if not root.exists():
        return []
    
    pages: List[Dict[str, Any]] = []
    for cat_dir in sorted(root.iterdir()):
        if not cat_dir.is_dir():
            continue
        cat = cat_dir.name
        for md_file in sorted(cat_dir.glob("*.md")):
            if partial and md_file.stem != partial and partial not in str(md_file):
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
                fm, body = _parse_frontmatter(text)
                if fm:
                    fm["_body"] = body
                    fm["_category"] = cat
                    fm["_path"] = str(md_file)
                    pages.append(fm)
            except Exception:
                continue
    
    return pages


def _parse_frontmatter(text: str) -> tuple:
    """Parse YAML frontmatter from Markdown."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        import yaml
        fm = yaml.safe_load(parts[1]) or {}
    except Exception:
        fm = _parse_simple_frontmatter(parts[1])
    return fm, parts[2].strip()


def _parse_simple_frontmatter(fm_text: str) -> Dict[str, Any]:
    """Fallback: parse key: value frontmatter without YAML."""
    result: Dict[str, Any] = {}
    for line in fm_text.strip().split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            # Handle lists: "[a, b, c]"
            if val.startswith("[") and val.endswith("]"):
                val = [v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()]
            result[key] = val
    return result


# ══════════════════════════════════════════════════════════════
# KB Document Scanner
# ══════════════════════════════════════════════════════════════

def _scan_kb_documents(partial: Optional[str] = None) -> List[Dict[str, Any]]:
    """Scan KB SQLite database for document records."""
    docs: List[Dict[str, Any]] = []
    kb_dir = Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))) / "kb" / "tenants"
    if not kb_dir.exists():
        return docs
    
    import sqlite3
    for tenant_dir in kb_dir.iterdir():
        if not tenant_dir.is_dir():
            continue
        db_path = tenant_dir / "kb.sqlite3"
        if not db_path.exists():
            continue
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            query = "SELECT doc_id, source_uri, kind, collection_id FROM documents"
            if partial:
                query += f" WHERE doc_id = '{partial}' OR collection_id = '{partial}'"
            rows = conn.execute(query).fetchall()
            for r in rows:
                docs.append({
                    "doc_id": r["doc_id"],
                    "source_uri": r["source_uri"] or "",
                    "kind": r["kind"] or "unknown",
                    "collection_id": r["collection_id"] or "",
                })
            conn.close()
        except Exception:
            continue
    
    return docs


# ══════════════════════════════════════════════════════════════
# Triple Builders
# ══════════════════════════════════════════════════════════════

def _build_wiki_triples(onto: KnowledgeOntology, pages: List[Dict[str, Any]]) -> None:
    """Build triples from Wiki page frontmatter data."""
    now = datetime.now(timezone.utc).isoformat()
    
    for fm in pages:
        title = str(fm.get("title", "")).strip()
        if not title:
            continue
        
        page_uri = f"{AI}{_safe_uri(title)}"
        category = str(fm.get("category", fm.get("_category", "entities")))
        
        # Class assignment
        if category == "entities":
            onto.triples.append(OntologyTriple(page_uri, "rdf:type", f"{AI}ConceptPage"))
        elif category == "topics":
            onto.triples.append(OntologyTriple(page_uri, "rdf:type", f"{AI}TopicPage"))
        else:
            onto.triples.append(OntologyTriple(page_uri, "rdf:type", f"{AI}WikiPage"))
        
        # Data properties
        _add_data(onto, page_uri, "title", str(title))
        _add_data(onto, page_uri, "category", category)
        
        summary = str(fm.get("summary", ""))[:300]
        if summary:
            _add_data(onto, page_uri, "summary", summary)
        
        tags = fm.get("tags", []) or []
        for t in (tags if isinstance(tags, list) else [tags]):
            _add_data(onto, page_uri, "tags", str(t))
        
        _add_data(onto, page_uri, "created_at", fm.get("created_at", now))
        _add_data(onto, page_uri, "updated_at", fm.get("last_updated", now))
        
        # Source articles → hasSource (only kb: prefix maps to KBDocument)
        for src in (fm.get("source_articles") or []):
            if isinstance(src, str) and src.strip() and src.startswith("kb:"):
                kb_uri = f"{AI}{_safe_uri(str(src))}"
                onto.triples.append(OntologyTriple(page_uri, f"{AI}hasSource", kb_uri))
        
        # Related → cites
        for rel in (fm.get("related") or []):
            if isinstance(rel, str) and rel.strip():
                target_uri = f"{AI}{_safe_uri(rel)}"
                onto.triples.append(OntologyTriple(page_uri, f"{AI}cites", target_uri))
        
        # Contradictions → contradicts
        for c in (fm.get("contradictions") or []):
            if isinstance(c, str) and c.strip():
                target_uri = f"{AI}{_safe_uri(c)}"
                onto.triples.append(OntologyTriple(page_uri, f"{AI}contradicts", target_uri))
                # A3: SymmetricProperty — contradiction goes both ways
                onto.triples.append(OntologyTriple(target_uri, f"{AI}contradicts", page_uri))
        
        # Typed relationships
        for rel in (fm.get("relationships") or []):
            if not isinstance(rel, dict):
                continue
            rel_type = str(rel.get("type", ""))
            target = str(rel.get("target", ""))
            if not rel_type or not target:
                continue
            target_uri = f"{AI}{_safe_uri(target)}"
            
            prop_map = {
                "cites": f"{AI}cites",
                "supports": f"{AI}supports",
                "contradicts": f"{AI}contradicts",
                "example_of": f"{AI}example_of",
                "extends": f"{AI}extends",
                "parent": f"{AI}parentOf",
                "derived_from": f"{AI}hasSource",
                "related": f"{AI}cites",
            }
            
            prop = prop_map.get(rel_type)
            if prop:
                onto.triples.append(OntologyTriple(page_uri, prop, target_uri))
                
                # parentOf → childOf inverse
                if rel_type == "parent":
                    onto.triples.append(OntologyTriple(target_uri, f"{AI}childOf", page_uri))
                
                # contradicts → enforce symmetry (A3)
                if rel_type == "contradicts":
                    onto.triples.append(OntologyTriple(target_uri, f"{AI}contradicts", page_uri))
        
        # Auto-detect SourcePage
        has_cites = any(t.predicate == f"{AI}cites" and t.subject == page_uri for t in onto.triples)
        if category == "entities" and not has_cites:
            onto.triples.append(OntologyTriple(page_uri, "rdf:type", f"{AI}SourcePage"))


def _build_kb_triples(onto: KnowledgeOntology, docs: List[Dict[str, Any]]) -> None:
    """Build triples from KB document records."""
    for d in docs:
        doc_uri = f"{AI}{_safe_uri(str(d.get('doc_id', '')))}"
        if not doc_uri:
            continue
        
        onto.triples.append(OntologyTriple(doc_uri, "rdf:type", f"{AI}KBDocument"))
        _add_data(onto, doc_uri, "doc_id", str(d.get("doc_id", "")))
        _add_data(onto, doc_uri, "kind", str(d.get("kind", "unknown")))
        _add_data(onto, doc_uri, "title", str(d.get("source_uri", ""))[:200])
        
        # Map to hasSource with correct URI
        # The Wiki pages reference KBDocument via strings like "kb:doc_xxx"
        # We need to create also the aliased version
        alias_uri = f"{AI}{_safe_uri('kb:' + str(d.get('doc_id', '')))}"
        if alias_uri != doc_uri:
            onto.triples.append(OntologyTriple(alias_uri, "rdf:type", f"{AI}KBDocument"))
            _add_data(onto, alias_uri, "doc_id", str(d.get("doc_id", "")))


def _cross_validate_sources(onto: KnowledgeOntology, pages: List[Dict[str, Any]], 
                            docs: List[Dict[str, Any]]) -> None:
    """Check that all hasSource references point to existing KBDocuments."""
    known_docs = {d["doc_id"] for d in docs}
    
    for t in onto.triples:
        if t.predicate == f"{AI}hasSource":
            # Extract doc_id from object URI
            obj_id = t.object.replace(AI, "")
            # Check if it matches any known KB document (by doc_id or aliased key)
            if obj_id not in known_docs:
                # Try stripping kb: prefix
                clean_id = obj_id.replace("kb:", "").split("_safe_uri")[0] if "kb:" in obj_id else obj_id
                if clean_id not in known_docs:
                    _add_data(onto, t.subject, "invalid_source", obj_id)


# ══════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════

def _add_data(onto: KnowledgeOntology, subject: str, prop: str, value: str) -> None:
    """Add a data property triple if the value is non-empty."""
    if value:
        onto.triples.append(OntologyTriple(
            subject, f"{AI}{prop}", f'"{value}"'
        ))


def _safe_uri(name: str) -> str:
    """Convert a name to a URI-safe string."""
    import re
    safe = re.sub(r'[<>:"/\\|?*#]', '_', str(name))
    return safe[:120]


# ══════════════════════════════════════════════════════════════
# Incremental Rebuild API
# ══════════════════════════════════════════════════════════════

def rebuild_for_doc(doc_id: str, *, collection_id: str = "default") -> KnowledgeOntology:
    """Incremental rebuild: only triples related to a specific KB document."""
    return build_abox(partial=doc_id, collection_id=collection_id)


def rebuild_for_page(title: str, *, collection_id: str = "default") -> KnowledgeOntology:
    """Incremental rebuild: only triples related to a specific Wiki page."""
    return build_abox(partial=title, collection_id=collection_id)


def rebuild_full(*, collection_id: str = "default") -> KnowledgeOntology:
    """Full A-Box rebuild from scratch."""
    reset_ontology()
    return build_abox(collection_id=collection_id)
