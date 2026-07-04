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
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from core.harness.knowledge.knowledge_ontology import KnowledgeOntology, OntologyTriple

AI = "http://aiplat.local/knowledge#"

logger = logging.getLogger(__name__)

# ── A-Box cache (module-level, 60s TTL, invalidated on wiki page writes) ──
_ABOX_CACHE: Dict[str, tuple] = {}  # collection_id → (timestamp, ontology)


def invalidate_abox_cache(collection_id: str = "default") -> None:
    """Invalidate cached A-Box for a collection. Call from write_page/delete_page."""
    _ABOX_CACHE.pop(collection_id, None)


def _wiki_root(collection_id: str = "default") -> Path:
    """Get wiki root for a specific collection, delegating to wiki_engine."""
    from core.harness.knowledge.wiki_engine import _wiki_root as _engine_wiki_root
    return _engine_wiki_root(collection_id)


def build_abox(partial: Optional[str] = None, *, collection_id: str = "default") -> KnowledgeOntology:
    """
    Build A-Box from current Wiki + KB data.
    Full rebuilds are cached per collection_id for 60s to avoid redundant computation.
    """
    # Check cache (full rebuild only; partial rebuilds are always fresh)
    if partial is None:
        cached = _ABOX_CACHE.get(collection_id)
        if cached:
            ts, onto = cached
            if time.time() - ts < 60:
                return onto

    from core.harness.knowledge.knowledge_ontology import get_ontology
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
    
    # ── Step 4: Cross-modal relation extraction ──
    _extract_cross_modal_relations(onto)
    
    logger.info(f"A-Box built: {len(onto.triples)} triples, {len(wiki_pages)} Wiki pages, "
                f"{len(kb_docs)} KB docs, {time.time() - start:.2f}s")

    # Cache full rebuilds
    if partial is None:
        _ABOX_CACHE[collection_id] = (time.time(), onto)

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
            conn = sqlite3.connect(str(db_path, timeout=5.0))
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
    from core.harness.knowledge.knowledge_ontology import OntologyTriple
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

        # Lifecycle state (Phase 1 — entity lifecycle state machine)
        lifecycle = fm.get("lifecycle_state", "published")
        _add_data(onto, page_uri, "lifecycleState", lifecycle)

        # Generation provenance
        gen = fm.get("_generated_by")
        if gen:
            import json as _json
            _add_data(onto, page_uri, "generatedBy", _json.dumps(gen, ensure_ascii=False) if isinstance(gen, dict) else str(gen))

        # Quality score (Phase 4 — accumulated from pipeline feedback)
        quality_score = fm.get("quality_score")
        if quality_score is not None:
            _add_data(onto, page_uri, "qualityScore", str(quality_score))

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
                "parentOf": f"{AI}parentOf",
                "childOf": f"{AI}childOf",
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
    from core.harness.knowledge.knowledge_ontology import OntologyTriple
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
    from core.harness.knowledge.knowledge_ontology import OntologyTriple
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
    from core.harness.knowledge.knowledge_ontology import reset_ontology
    reset_ontology()
    return build_abox(collection_id=collection_id)


def _extract_cross_modal_relations(onto: KnowledgeOntology) -> None:
    u"""Extract cross-modal relations from KB elements.

    Scans kb_elements table for text→image, text→table, and image→section
    relationships based on page proximity and keyword matching.

    Relations created:
      - AI:refersToImage: text element mentions image on same/adjacent page
      - AI:refersToTable: text element mentions table on same/adjacent page
      - AI:explains: text explains a table/image on same page
      - AI:belongsToSection: image/table belongs to the nearest section heading
    """
    import sqlite3

    kb_dir = Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))) / "kb" / "tenants"
    if not kb_dir.exists():
        return

    from core.harness.knowledge.knowledge_ontology import OntologyTriple

    for tenant_dir in kb_dir.iterdir():
        if not tenant_dir.is_dir():
            continue
        db_path = tenant_dir / "kb.sqlite3"
        if not db_path.exists():
            continue

        try:
            conn = sqlite3.connect(str(db_path, timeout=5.0))
            conn.row_factory = sqlite3.Row

            # Load all elements grouped by doc_id + page
            rows = conn.execute(
                "SELECT element_id, doc_id, type, page_idx, text, bbox_json "
                "FROM kb_elements WHERE type IN ('text', 'table', 'image') "
                "ORDER BY doc_id, page_idx, element_id"
            ).fetchall()
            conn.close()

            if not rows:
                continue

            # Group by (doc_id, page_idx)
            by_page: dict = {}
            for r in rows:
                key = (r["doc_id"], r["page_idx"] or 0)
                by_page.setdefault(key, []).append(dict(r))

            for (doc_id, page), elements in by_page.items():
                texts = [e for e in elements if e["type"] == "text"]
                tables = [e for e in elements if e["type"] == "table"]
                images = [e for e in elements if e["type"] == "image"]

                # 1. Text → Image/Table references by keyword
                IMAGE_KEYWORDS = ("如图", "见图", "下图", "上图", "图中", "如下面图", "如下图的")
                TABLE_KEYWORDS = ("如下表", "下表", "上表", "见表", "表中", "如表中", "如下面表")

                for text_elem in texts:
                    txt = (text_elem.get("text") or "").lower()

                    for img_kw in IMAGE_KEYWORDS:
                        if img_kw.lower() in txt:
                            for img_elem in images:
                                text_uri = f"{AI}kb_elem_{text_elem['element_id']}"
                                img_uri = f"{AI}kb_elem_{img_elem['element_id']}"
                                onto.triples.append(
                                    OntologyTriple(text_uri, f"{AI}refersToImage", img_uri)
                                )
                                onto.triples.append(
                                    OntologyTriple(text_uri, f"{AI}explains", img_uri)
                                )
                            break  # match once per text element per keyword type

                    for tbl_kw in TABLE_KEYWORDS:
                        if tbl_kw.lower() in txt:
                            for tbl_elem in tables:
                                text_uri = f"{AI}kb_elem_{text_elem['element_id']}"
                                tbl_uri = f"{AI}kb_elem_{tbl_elem['element_id']}"
                                onto.triples.append(
                                    OntologyTriple(text_uri, f"{AI}refersToTable", tbl_uri)
                                )
                                onto.triples.append(
                                    OntologyTriple(text_uri, f"{AI}explains", tbl_uri)
                                )
                            break

                # 2. Image/Table → nearest section heading
                # Find the first text element on this page that looks like a heading
                headings = [
                    t for t in texts
                    if (t.get("text") or "").strip() and len((t.get("text") or "").strip()) < 80
                    and not any(kw in (t.get("text") or "").lower() for kw in ("如图", "下表", "见图", "见表"))
                ]
                if headings:
                    section_uri = f"{AI}kb_elem_{headings[0]['element_id']}"
                    for tbl_elem in tables:
                        onto.triples.append(
                            OntologyTriple(f"{AI}kb_elem_{tbl_elem['element_id']}", f"{AI}belongsToSection", section_uri)
                        )
                    for img_elem in images:
                        onto.triples.append(
                            OntologyTriple(f"{AI}kb_elem_{img_elem['element_id']}", f"{AI}belongsToSection", section_uri)
                        )

        except Exception:
            continue
