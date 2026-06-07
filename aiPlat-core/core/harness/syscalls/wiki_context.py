"""
sys_wiki_context — Wiki knowledge context for Agents.

Combines semantic search (embedding) with keyword search (FTS5) and
link-graph traversal to return comprehensive knowledge context.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def sys_wiki_context(question: str, *, wiki_titles: List[str] = None,
                     top_k: int = 8, link_depth: int = 1,
                     collection_ids: List[str] = None) -> Dict[str, Any]:
    u"""Return knowledge context for a question from the Wiki knowledge graph.

    Combines:
      1. FTS5 keyword search (exact name match)
      2. Embedding semantic search (wiki_retrieve)
      3. Link-graph traversed related pages

    Args:
        collection_ids: Wiki collections to search. Defaults to ["default"].

    Returns:
      {results: [{title, text, score, tags, summary, source}],
       fts5_matches: [title],
       related_pages: [{title, summary}]}
    """
    from core.harness.knowledge.wiki_engine import search_pages, traverse_links
    from core.harness.syscalls.retrieval import sys_wiki_retrieve

    cids = collection_ids or ["default"]

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

    return {
        "results": results,
        "fts5_matches": fts5_matches,
        "related_pages": related_pages[:10],
    }
