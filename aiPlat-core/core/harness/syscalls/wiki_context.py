"""
sys_wiki_context — Wiki knowledge context for Agents.

Combines semantic search (embedding) with keyword search (FTS5) and
link-graph traversal to return comprehensive knowledge context.

Phase 2: optional marking-aware filtering via actor_scopes parameter.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def sys_wiki_context(question: str, *, wiki_titles: List[str] = None,
                     top_k: int = 8, link_depth: int = 1,
                     collection_ids: List[str] = None,
                     actor_scopes: Optional[List[str]] = None,
                     filter_by_markings: bool = False) -> Dict[str, Any]:
    u"""Return knowledge context for a question from the Wiki knowledge graph.

    Combines:
      1. FTS5 keyword search (exact name match)
      2. Embedding semantic search (wiki_retrieve)
      3. Link-graph traversed related pages

    Args:
        collection_ids: Wiki collections to search. Defaults to ["default"].
        actor_scopes: optional scopes for marking-aware filtering.
        filter_by_markings: if True, exclude entities the actor cannot access.

    Returns:
      {results: [{title, text, score, tags, summary, source}],
       fts5_matches: [title],
       related_pages: [{title, summary}]}

    边界:
      - 只读——不从 Wiki 页面读取中产生写操作
      - FTS5 和语义检索的分数不可直接比较
      - filter_by_markings=True 时结果可能少于 top_k
    退路:
      - 需要全文 → 用 wiki_engine.read_page() 直接读取
      - 需要文档检索 → sys_kb_retrieve
    """
    from core.harness.knowledge.wiki_engine import search_pages, traverse_links
    from core.harness.syscalls.retrieval import sys_wiki_retrieve

    cids = collection_ids or ["default"]

    # Phase QM: ontology-aware query rewriting
    try:
        from core.harness.knowledge.ontology_query_mapper import enrich_query_for_retrieval
        question = enrich_query_for_retrieval(question, collection_id=cids[0])
    except Exception:
        pass

    # FTS5 keyword search
    fts5_matches: List[str] = []
    try:
        from core.harness.knowledge.wiki_fts import fts_search
        fts5_matches = [r["title"] for r in fts_search(question, limit=5)]
    except ImportError:
        pass

    # Semantic search via wiki retriever
    results = sys_wiki_retrieve(question, wiki_titles=wiki_titles, top_k=top_k,
                                 link_depth=link_depth, collection_ids=cids)

    # Link-graph traversed related pages for top results
    related_pages: List[Dict[str, Any]] = []
    seen: set = set()
    for r in results[:3]:
        title = r.get("title", "")
        if title and title not in seen:
            try:
                for cid in cids:
                    linked = traverse_links(title, depth=link_depth, collection_id=cid)
                    for lp in linked:
                        if lp["title"] not in seen:
                            seen.add(lp["title"])
                            related_pages.append({"title": lp["title"],
                                                  "summary": lp.get("summary", "")[:120]})
            except Exception:
                pass

    # Phase CM: cross-modal relation traversal
    AI = "http://aiplat.local/knowledge#"
    try:
        from core.harness.knowledge.knowledge_ontology import get_ontology
        onto = get_ontology()
        cross_modal_related: List[Dict[str, str]] = []
        for r in results[:5]:
            title = r.get("title", "")
            if not title:
                continue
            for t in onto.triples:
                if t.subject and title in t.subject and t.predicate in (
                    f"{AI}refersToImage", f"{AI}refersToTable", f"{AI}explains",
                ):
                    target_name = t.object.replace(AI, "")
                    if target_name not in [c.get("title", "") for c in cross_modal_related]:
                        cross_modal_related.append({"title": target_name, "summary": f"cross-modal reference (via {t.predicate.replace(AI, '')})"})
        related_pages[:0] = cross_modal_related[:5]
    except Exception:
        pass

    # Phase AligNet: three-tier abstraction retrieval (coarse/fine/boundary)
    abstraction_results: List[Dict[str, Any]] = []
    try:
        from core.harness.knowledge.knowledge_ontology import get_ontology
        onto = get_ontology()

        # Tier 1 — Coarse: parentOf hierarchy matching
        for r in results[:8]:
            title = r.get("title", "")
            if not title:
                continue
            entity_uri = f"{AI}{title}"
            for t in onto.triples:
                if t.subject == entity_uri and t.predicate == f"{AI}parentOf":
                    parent = t.object.replace(AI, "")
                    abstraction_results.append({
                        "title": parent, "tier": "coarse",
                        "relation": "parentOf", "summary": f"parent concept of {title}",
                    })
                if t.predicate == f"{AI}parentOf" and t.object == entity_uri:
                    child = t.subject.replace(AI, "")
                    abstraction_results.append({
                        "title": child, "tier": "coarse",
                        "relation": "childOf", "summary": f"child concept of {title}",
                    })

        # Tier 3 — Boundary: A8 key discrimination check
        seen_titles = set()
        from core.harness.knowledge.knowledge_ontology import check_key_discrimination
        for r in results[:5]:
            title = r.get("title", "")
            if not title:
                continue
            ok, warnings = check_key_discrimination(title, str(r.get("summary", ""))[:100])
            if not ok:
                for w in warnings[:2]:
                    similar = w.split("with existing '")[-1].split("'")[0] if "with existing" in w else ""
                    if similar and similar not in seen_titles:
                        seen_titles.add(similar)
                        abstraction_results.append({
                            "title": similar, "tier": "boundary",
                            "relation": "near_duplicate",
                            "summary": f"A8: key too similar to '{title}', consider merge",
                        })
    except Exception:
        pass

    # Merge abstraction results into related pages
    existing_titles = {r.get("title", "") for r in results + related_pages}
    for ar in abstraction_results[:10]:
        if ar.get("title", "") and ar["title"] not in existing_titles:
            related_pages.append(ar)

    # Phase 2: marking-aware filtering
    if filter_by_markings and actor_scopes:
        results = _filter_by_markings(results, actor_scopes, cids[0])
        related_pages = _filter_by_markings(related_pages, actor_scopes, cids[0])

    # Phase FLS: field-level security — redact sensitive fields
    if actor_scopes:
        results = _apply_field_level_security(results, actor_scopes, cids[0])

    return {
        "results": results,
        "fts5_matches": fts5_matches,
        "related_pages": related_pages[:10],
    }


def _filter_by_markings(
    items: List[Dict[str, Any]],
    actor_scopes: List[str],
    collection_id: str,
) -> List[Dict[str, Any]]:
    u"""Filter a list of wiki results, removing items the actor cannot access."""
    if not items or "admin" in actor_scopes:
        return items

    try:
        from core.harness.knowledge.knowledge_markings import (
            load_markings_config, resolve_effective_markings, MarkingLevel,
        )
        from core.harness.knowledge.knowledge_ontology import get_ontology
        from core.harness.knowledge.knowledge_abox_builder import _safe_uri

        AI = "http://aiplat.local/knowledge#"
        marking_config = load_markings_config(collection_id)
        onto = get_ontology()

        filtered = []
        for item in items:
            title = item.get("title", "")
            if not title:
                filtered.append(item)
                continue

            entity_uri = f"{AI}{_safe_uri(title)}"
            effective, _ = resolve_effective_markings(
                entity_uri, marking_config, onto.triples, max_depth=5,
            )

            blocked = False
            for m in effective:
                if m.level >= MarkingLevel.INTERNAL:
                    required_scope = m.scope or f"kb:read:{m.label.lower()}"
                    if required_scope not in set(actor_scopes):
                        blocked = True
                        break
            if not blocked:
                filtered.append(item)

        return filtered
    except Exception:
        return items  # best-effort: return unfiltered on error


def _apply_field_level_security(
    items: List[Dict[str, Any]],
    actor_scopes: List[str],
    collection_id: str,
) -> List[Dict[str, Any]]:
    u"""Apply field-level security redaction to wiki results."""
    if not items or "admin" in actor_scopes:
        return items

    try:
        from core.policy.field_level_security import apply_field_level_security
        from core.harness.knowledge.knowledge_abox_builder import _safe_uri
        AI = "http://aiplat.local/knowledge#"

        results = []
        for item in items:
            title = item.get("title", "")
            entity_uri = f"{AI}{_safe_uri(title)}" if title else ""
            safe = apply_field_level_security(
                item, entity_uri,
                actor_scopes=actor_scopes,
                collection_id=collection_id,
            )
            results.append(safe)
        return results
    except Exception:
        return items
