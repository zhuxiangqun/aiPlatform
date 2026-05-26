"""
WikiPageRetriever — IRetriever implementation for wiki knowledge pages.

Reads wiki markdown pages from ~/.aiplat/wiki/, embeds via infra
InfraEmbeddingAdapter, and returns KnowledgeResult objects compatible
with the existing KnowledgeRetriever pipeline.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .retriever import IRetriever
from .types import (
    KnowledgeEntry, KnowledgeQuery, KnowledgeResult,
    KnowledgeType, KnowledgeSource, KnowledgeMetadata, KnowledgeStatus,
)


class WikiPageRetriever(IRetriever):
    """Retrieve knowledge from wiki pages by semantic similarity.

    Pages are read from disk via wiki_engine. Embedding uses
    embed_text_semantic() → InfraEmbeddingAdapter → infra ModelManager.
    """

    def __init__(self, wiki_titles: List[str] = None, link_depth: int = 0):
        self._wiki_titles = wiki_titles or []
        self._link_depth = link_depth
        self._entries: Dict[str, KnowledgeEntry] = {}

    def _load_pages(self) -> List[Dict[str, Any]]:
        from core.harness.knowledge.wiki_engine import read_page, search_pages

        titles = set(self._wiki_titles)
        # If no titles specified, load all pages
        if not titles:
            all_pages = search_pages(limit=1000)
            for p in all_pages:
                titles.add(p["title"])

        # BFS traverse [[links]] if link_depth > 0
        if self._link_depth > 0:
            from core.harness.knowledge.wiki_engine import traverse_links
            for start in list(titles):
                linked = traverse_links(start, depth=self._link_depth)
                for lp in linked:
                    titles.add(lp["title"])

        pages = []
        for t in titles:
            p = read_page(t)
            if p and p.get("body"):
                pages.append(p)
        return pages

    async def retrieve(self, query: KnowledgeQuery) -> List[KnowledgeResult]:
        from core.harness.knowledge.embedder import embed_text_semantic, embed_texts_semantic, cosine_similarity

        pages = self._load_pages()
        if not pages:
            return []

        qvec = embed_text_semantic(query.query[:2000])
        if qvec is None:
            return []

        texts = [(p["body"] or "")[:5000] for p in pages]
        pvecs = embed_texts_semantic(texts)

        results = []
        for i, (page, pvec) in enumerate(zip(pages, pvecs)):
            if pvec is None:
                continue
            sim = cosine_similarity(qvec, pvec)
            entry = KnowledgeEntry(
                id=f"wiki:{page['title']}",
                type=KnowledgeType.CONCEPT if page.get("category") == "topics" else KnowledgeType.FACT,
                content=page.get("body", ""),
                title=page["title"],
                summary=page.get("summary", ""),
                metadata=KnowledgeMetadata(
                    source=KnowledgeSource.SYSTEM,
                    tags=page.get("tags", [])[:8],
                    confidence=min(1.0, max(0.0, sim)),
                    relevance=sim,
                ),
                references=page.get("source_articles", []),
            )
            highlight = page["title"]
            if page.get("summary"):
                highlight += f": {page['summary'][:120]}"
            results.append(KnowledgeResult(entry=entry, score=sim, highlight=highlight))
            self._entries[entry.id] = entry

        results.sort(key=lambda r: -r.score)
        return results[:query.limit or 10]

    async def get_by_id(self, entry_id: str) -> Optional[KnowledgeEntry]:
        if entry_id in self._entries:
            return self._entries[entry_id]
        # Lazy load single page
        title = entry_id.replace("wiki:", "", 1)
        from core.harness.knowledge.wiki_engine import read_page
        page = read_page(title)
        if not page:
            return None
        entry = KnowledgeEntry(
            id=f"wiki:{title}",
            type=KnowledgeType.CONCEPT,
            content=page.get("body", ""),
            title=title,
            summary=page.get("summary", ""),
            metadata=KnowledgeMetadata(source=KnowledgeSource.SYSTEM, tags=page.get("tags", [])),
        )
        self._entries[entry.id] = entry
        return entry

    async def get_similar(self, entry: KnowledgeEntry, limit: int = 10) -> List[KnowledgeResult]:
        from core.harness.knowledge.embedder import embed_text_semantic, embed_texts_semantic, cosine_similarity
        pages = self._load_pages()
        if not pages or not entry.title:
            return []
        target_text = entry.content or entry.title
        target_vec = embed_text_semantic(target_text[:2000])
        if target_vec is None:
            return []
        texts = [(p["body"] or "")[:5000] for p in pages if p["title"] != entry.title]
        pvecs = embed_texts_semantic(texts)
        results = []
        for i, (page, pvec) in enumerate(zip(
            [p for p in pages if p["title"] != entry.title], pvecs
        )):
            if pvec is None: continue
            sim = cosine_similarity(target_vec, pvec)
            e = KnowledgeEntry(
                id=f"wiki:{page['title']}", type=KnowledgeType.CONCEPT,
                content=page.get("body", ""), title=page["title"],
                metadata=KnowledgeMetadata(source=KnowledgeSource.SYSTEM, tags=page.get("tags", [])),
            )
            results.append(KnowledgeResult(entry=e, score=sim))
        results.sort(key=lambda r: -r.score)
        return results[:limit]

    async def add(self, entry: KnowledgeEntry) -> None:
        self._entries[entry.id] = entry

    async def add_batch(self, entries: List[KnowledgeEntry]) -> None:
        for e in entries:
            self._entries[e.id] = e
