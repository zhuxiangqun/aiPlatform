"""
WikiPageRetriever — IRetriever implementation for wiki knowledge pages.

Reads wiki markdown pages from ~/.aiplat/wiki/, embeds via infra
InfraEmbeddingAdapter, and returns KnowledgeResult objects compatible
with the existing KnowledgeRetriever pipeline.
"""

from __future__ import annotations
import logging

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

    def __init__(self, wiki_titles: List[str] = None, link_depth: int = 0, collection_ids: List[str] = None,
                 # ── Ontology-aware filtering ──
                 class_uri: str = None,
                 expand_subclasses: bool = False,
                 relation_filter: Dict[str, str] = None,
                 relation_boost: Dict[str, float] = None,
                 # ── Inference expansion ──
                 inference_expand: bool = False,
                 # ── Multi-tenant isolation ──
                 tenant_id: str = "",
                 ):
        self._wiki_titles = wiki_titles or []
        self._link_depth = link_depth
        self._collection_ids = collection_ids or ["default"]
        self._class_uri = class_uri
        self._expand_subclasses = expand_subclasses
        self._relation_filter = relation_filter or {}
        self._relation_boost = relation_boost or {}
        self._inference_expand = inference_expand
        self._tenant_id = tenant_id
        self._entries: Dict[str, KnowledgeEntry] = {}

    def _load_pages(self) -> List[Dict[str, Any]]:
        from core.harness.knowledge.wiki_engine import read_page, search_pages

        titles = set(self._wiki_titles)
        # If no titles specified, load all pages from bound collections
        if not titles:
            for cid in self._collection_ids:
                all_pages = search_pages(limit=1000, collection_id=cid)
                for p in all_pages:
                    titles.add(p["title"])

        # BFS traverse [[links]] if link_depth > 0
        if self._link_depth > 0:
            from core.harness.knowledge.wiki_engine import traverse_links
            for start in list(titles):
                for cid in self._collection_ids:
                    linked = traverse_links(start, depth=self._link_depth, collection_id=cid)
                    for lp in linked:
                        titles.add(lp["title"])

        pages = []
        for t in titles:
            for cid in self._collection_ids:
                p = read_page(t, collection_id=cid)
                if p and p.get("body"):
                    pages.append(p)
                    break

        # ── Inject cached vectors ──
        try:
            from pathlib import Path
            cid = self._collection_ids[0] if self._collection_ids else "default"
            cache_path = Path.home() / ".aiplat" / "wiki" / "collections" / cid / "vectors.json"
            if cache_path.exists():
                import json as _json
                cache = _json.loads(cache_path.read_text(encoding="utf-8"))
                for p in pages:
                    if p["title"] in cache:
                        p["_cached_vector"] = cache[p["title"]]
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        return pages

    def _filter_by_class(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter pages by T-Box class and optionally expand to subclasses."""
        if not self._class_uri:
            return pages

        from core.harness.knowledge.knowledge_ontology import CLASSES, get_ontology

        onto = get_ontology()
        target_classes = {self._class_uri}

        if self._expand_subclasses:
            for cls in CLASSES:
                # Walk parent chain to see if cls is a descendant of any target class
                current = cls
                while current.parent:
                    if current.parent in target_classes:
                        target_classes.add(cls.uri)
                        break
                    parent = next((c for c in CLASSES if c.uri == current.parent), None)
                    if parent is None:
                        break
                    current = parent

        class_categories: set = set()
        for cls in CLASSES:
            if cls.uri in target_classes:
                class_categories.update(cls.allowed_categories)

        if not class_categories:
            return pages

        return [p for p in pages if p.get("category") in class_categories]

    def _parse_relation_query(self, query_text: str) -> Optional[Dict[str, str]]:
        """Parse natural language query into a structured relation filter.

        Maps Chinese patterns to ontology object properties:
          支撑X的概念 → {"supports": "X"}
          与X矛盾的页面 → {"contradicts": "X"}
          X的案例 → {"example_of": "X"}
          X的子概念 → {"childOf": "X"}
        """
        import re

        # Relation pattern keywords → ontology property mapping
        keywords = [
            ("支撑", "supports"),
            ("矛盾", "contradicts"),
            ("冲突", "contradicts"),
            ("案例", "example_of"),
            ("子概念", "childOf"),
            ("子类", "childOf"),
            ("下级", "childOf"),
            ("父概念", "parentOf"),
            ("父类", "parentOf"),
            ("上级", "parentOf"),
            ("引用", "cites"),
            ("关联", "cites"),
        ]

        for kw, rel in keywords:
            if kw in query_text:
                # Extract the target name (the thing being related to/from)
                # Pattern: "支撑X" or "X的案例" or "与X矛盾"
                target = ""
                if kw in ("支撑",):
                    m = re.search(r"支撑\s*(\S+)", query_text)
                    if m: target = m.group(1)
                elif kw in ("矛盾", "冲突"):
                    m = re.search(r"(?:与|和)\s*(\S+?)\s*(?:矛盾|冲突)", query_text)
                    if m: target = m.group(1)
                elif kw in ("案例",):
                    m = re.search(r"(\S+)\s*的?\s*案例", query_text)
                    if m: target = m.group(1)
                elif kw in ("子概念", "子类", "下级"):
                    m = re.search(r"(\S+)\s*的?\s*(?:子概念|子类|下级)", query_text)
                    if m: target = m.group(1)
                elif kw in ("父概念", "父类", "上级"):
                    m = re.search(r"(\S+)\s*的?\s*(?:父概念|父类|上级)", query_text)
                    if m: target = m.group(1)
                elif kw in ("引用", "关联"):
                    m = re.search(r"(\S+)\s*(?:引用|关联)\s*的?\s*页面", query_text)
                    if m: target = m.group(1)

                if target and len(target) > 1:
                    # Strip trailing particles and relation suffixes
                    target = re.sub(r"(的|的页面|的概念|的知识)$", "", target).strip()
                    if target and len(target) > 1:
                        return {rel: target}

        return None

    def _expand_by_inference(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Expand page pool with inference results (transitive closure, source chains)."""
        if not self._inference_expand:
            return pages

        from core.harness.knowledge.knowledge_abox_builder import build_abox
        from core.harness.knowledge.knowledge_validator import TripleStore, run_full_inference, _short
        import time as _time, json as _cache_json
        from pathlib import Path as _Path

        # ── Inference cache: merge across all collections ──
        merged = {"transitive": [], "source_chain": []}
        any_stale = False

        for cid in self._collection_ids:
            cache_path = _Path.home() / ".aiplat" / "wiki" / "collections" / cid / "inference_cache.json"
            if cache_path.exists():
                try:
                    cache_data = _cache_json.loads(cache_path.read_text(encoding="utf-8"))
                    if _time.time() - cache_data.get("ts", 0) < 3600:
                        inf = cache_data.get("inference", {})
                        merged["transitive"].extend(inf.get("transitive", []))
                        merged["source_chain"].extend(inf.get("source_chain", []))
                    else:
                        any_stale = True
                except Exception:
                    any_stale = True
            else:
                any_stale = True

        # If any collection needs fresh inference, rebuild primary
        if any_stale:
            primary_cid = self._collection_ids[0] if self._collection_ids else "default"
            try:
                onto = build_abox(collection_id=primary_cid)
                store = TripleStore(onto.triples)
                inference = run_full_inference(store)
                merged["transitive"] = inference.get("transitive", [])
                merged["source_chain"] = inference.get("source_chain", [])
                cache_path = _Path.home() / ".aiplat" / "wiki" / "collections" / primary_cid / "inference_cache.json"
                cache_path.write_text(_cache_json.dumps(
                    {"ts": _time.time(), "inference": inference}, ensure_ascii=False))
                # For secondary collections, trigger async build if possible
                for cid in self._collection_ids[1:]:
                    try:
                        onto2 = build_abox(collection_id=cid)
                        store2 = TripleStore(onto2.triples)
                        inf2 = run_full_inference(store2)
                        merged["transitive"].extend(inf2.get("transitive", []))
                        merged["source_chain"].extend(inf2.get("source_chain", []))
                        cp2 = _Path.home() / ".aiplat" / "wiki" / "collections" / cid / "inference_cache.json"
                        cp2.write_text(_cache_json.dumps(
                            {"ts": _time.time(), "inference": inf2}, ensure_ascii=False))
                    except Exception as e:
                        logging.debug(str(e), exc_info=True)
            except Exception:
                return pages

        inference = merged

        existing_titles = {p["title"] for p in pages}
        expanded_titles: set = set()

        for kind in ("transitive", "source_chain"):
            for inf in inference.get(kind, []):
                subj = _short(inf["subject"])
                obj = _short(inf["object"])
                if subj in existing_titles and obj not in existing_titles:
                    expanded_titles.add(obj)
                if obj in existing_titles and subj not in existing_titles:
                    expanded_titles.add(subj)

        if expanded_titles:
            from core.harness.knowledge.wiki_engine import read_page
            for t in list(expanded_titles)[:50]:
                p = read_page(t, collection_id=cid)
                if p and p.get("body"):
                    pages.append(p)

        return pages

    def _load_relations_for_boost(self, page_title: str) -> Dict[str, float]:
        """Load page relations for scoring boost."""
        from core.harness.knowledge.wiki_engine import read_page
        boost = {}
        try:
            page = read_page(page_title, collection_id=self._collection_ids[0] if self._collection_ids else "default")
            if page:
                relationships = page.get("relationships") or []
                for rel in relationships:
                    if isinstance(rel, dict):
                        rtype = rel.get("type", "")
                        w = self._relation_boost.get(rtype, 0.0)
                        if w:
                            boost[f"{page_title}->{rtype}->{rel.get('target','')}"] = w
                # Also check related list
                for r in (page.get("related") or []):
                    w = self._relation_boost.get("related", 0.0)
                    if w:
                        boost[f"{page_title}->related->{r}"] = w
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        return boost

    def _fts_wiki_ranks(self, query: str, top_n: int = 30) -> Dict[str, float]:
        """Get FTS5 keyword search ranks for RRF fusion.
        Returns {title: normalized_rank_score} where rank_score = 1/(60 + rank + 1).
        """
        ranks: Dict[str, float] = {}
        try:
            from core.harness.knowledge.wiki_fts import fts_search
            fts_results = fts_search(query, limit=top_n)
            for i, r in enumerate(fts_results):
                title = r.get("title", "")
                if title:
                    ranks[title] = 1.0 / (60 + i + 1)
        except ImportError:
            pass
        return ranks

    async def retrieve(self, query: KnowledgeQuery) -> List[KnowledgeResult]:
        """Retrieve wiki pages via embedding semantic search.
        
        Multi-tenant isolation: uses self._collection_ids (set by caller via collection routing).
        query.tenant_id is cross-validated against self._tenant_id for defense-in-depth —
        mismatch is logged at WARNING but does not block retrieval (collection_ids are the
        actual filtering boundary).
        """
        # ── Defense-in-depth: cross-validate tenant_id ──
        if self._tenant_id and query.tenant_id and self._tenant_id != query.tenant_id:
            import logging
            logging.getLogger("wiki_retriever").error(
                "tenant_id mismatch: caller=%s retriever=%s — BLOCKING retrieval (security)",
                query.tenant_id, self._tenant_id)
            return []  # Security: tenant mismatch → empty results, not just warning
        
        from core.harness.knowledge.embedder import embed_text_semantic, embed_texts_semantic, cosine_similarity

        pages = self._load_pages()

        # ── Ontology: class filter ──
        pages = self._filter_by_class(pages)

        # ── Inference: expand page pool ──
        pages = self._expand_by_inference(pages)

        # ── Ontology: relation constraint filter ──
        # R2: Auto-detect relation patterns from natural language query
        effective_relation = self._relation_filter or {}
        if not effective_relation:
            auto_relation = self._parse_relation_query(query.query)
            if auto_relation:
                effective_relation = auto_relation

        if effective_relation:
            from core.harness.knowledge.wiki_engine import read_page
            rel_type = list(effective_relation.keys())[0]
            target = effective_relation[rel_type]
            target_page = read_page(target, collection_id=self._collection_ids[0] if self._collection_ids else "default")
            if target_page:
                related = target_page.get("related", [])
                pages = [p for p in pages if p["title"] in related]

        if not pages:
            return []

        qvec = embed_text_semantic(query.query[:2000])
        if qvec is None:
            return []

        # ── Use cached vectors where available, embed missing ones ──
        cached_pvecs = []
        missing_indices = []
        for i, p in enumerate(pages):
            cv = p.get("_cached_vector")
            if cv:
                cached_pvecs.append((i, cv))
            else:
                missing_indices.append(i)

        if missing_indices:
            missing_texts = [(pages[i]["body"] or "")[:5000] for i in missing_indices]
            missing_pvecs = embed_texts_semantic(missing_texts)
            # Persist computed vectors to cache for future retrievals
            try:
                from pathlib import Path
                cid = self._collection_ids[0] if self._collection_ids else "default"
                cache_path = Path.home() / ".aiplat" / "wiki" / "collections" / cid / "vectors.json"
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                import json as _json
                cache = {}
                if cache_path.exists():
                    try:
                        cache = _json.loads(cache_path.read_text(encoding="utf-8"))
                    except Exception:
                        cache = {}
                for j, pv in zip(missing_indices, missing_pvecs):
                    if pv is not None:
                        cache[pages[j]["title"]] = list(pv) if hasattr(pv, '__iter__') else pv
                cache_path.write_text(_json.dumps(cache, ensure_ascii=False))
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        else:
            missing_pvecs = []

        # Reconstruct full pvecs array in page order
        pvecs = [None] * len(pages)
        for idx, cv in cached_pvecs:
            pvecs[idx] = cv
        for j, pv in zip(missing_indices, missing_pvecs):
            pvecs[j] = pv

        # ── FTS5 keyword ranks for RRF blending ──
        fts_ranks = self._fts_wiki_ranks(query.query, top_n=30)

        results = []
        for i, (page, pvec) in enumerate(zip(pages, pvecs)):
            if pvec is None:
                continue
            sim = cosine_similarity(qvec, pvec)

            # ── FTS5 keyword boost (RRF-compatible blend) ──
            fts_score = fts_ranks.get(page["title"], 0.0)

            # ── Post-retrieval governance: freshness, credibility, density ──
            try:
                from core.harness.knowledge.post_retrieval_governor import (
                    _compute_freshness, _compute_credibility, _compute_density, GovernorConfig)
                _gov_cfg = GovernorConfig()
                freshness = _compute_freshness(page.get("last_updated", ""), _gov_cfg)
                credibility = _compute_credibility("wiki")
                density = _compute_density(page.get("body", "") or page.get("summary", ""))
            except Exception:
                freshness = 0.5
                credibility = 0.5
                density = 0.3

            # Composite score: semantic + keyword + governance factors
            cfg = _load_scoring_weights()
            sim = (sim * cfg["semantic"]
                   + fts_score * cfg["fts_keyword"]
                   + freshness * cfg["freshness"]
                   + credibility * cfg["credibility"]
                   + density * cfg["density"])

            # ── Ontology: relation boost ──
            if self._relation_boost:
                rel_boost = self._load_relations_for_boost(page["title"])
                max_boost = max(rel_boost.values()) if rel_boost else 0.0
                sim = sim * 0.7 + max_boost * 0.3

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
            results.append(KnowledgeResult(
                entry=entry, score=sim, highlight=highlight,
                source_page=page.get("title", ""),
                source_category=page.get("category", ""),
                evidence_range=page.get("body", "")[:200] if page.get("body") else "",
            ))
            self._entries[entry.id] = entry

        # ── Contradiction-aware: surface conflicting pages ──
        try:
            from core.harness.knowledge.knowledge_abox_builder import build_abox
            top_titles = {r.entry.title for r in results[:5]}
            onto = build_abox(collection_id=self._collection_ids[0] if self._collection_ids else "default")
            contradict_triples: Dict[str, set] = {}
            for t in onto.triples:
                if "contradicts" in str(t.predicate) and str(t.subject) in top_titles:
                    contradict_triples.setdefault(str(t.subject), set()).add(str(t.object))
            if contradict_triples:
                from core.harness.knowledge.wiki_engine import read_page
                seen_titles = {r.entry.title for r in results}
                for _src, targets in contradict_triples.items():
                    for target in targets:
                        clean_target = target.split("#")[-1] if "#" in target else target
                        if clean_target in seen_titles:
                            continue
                        try:
                            cp = read_page(clean_target,
                                           collection_id=self._collection_ids[0] if self._collection_ids else "default")
                            if cp:
                                c_entry = KnowledgeEntry(
                                    id=f"wiki:{clean_target}",
                                    type=KnowledgeType.CONCEPT,
                                    content=cp.get("body", "")[:1000],
                                    title=clean_target,
                                    summary=cp.get("summary", ""),
                                    metadata=KnowledgeMetadata(
                                        source=KnowledgeSource.SYSTEM,
                                        tags=cp.get("tags", [])[:8],
                                        confidence=0.3,  # lower confidence: contradictory
                                        relevance=0.3,
                                    ),
                                    references=cp.get("source_articles", []),
                                )
                                c_highlight = f"⚠️ 矛盾观点: {clean_target}"
                                if cp.get("summary"):
                                    c_highlight += f": {cp['summary'][:80]}"
                                results.append(KnowledgeResult(
                                    entry=c_entry, score=0.25, highlight=c_highlight,
                                    source_page=clean_target,
                                    source_category="contradictions",
                                    evidence_range="contradiction_with:" + result.entry.title[:40],
                                ))
                                self._entries[c_entry.id] = c_entry
                                seen_titles.add(clean_target)
                        except Exception as e:
                            logging.debug(str(e), exc_info=True)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        results.sort(key=lambda r: -r.score)

        # ── Lightweight reranker (zero-model, <1ms) when results > limit ──
        limit = query.limit or 10
        if len(results) > limit:
            try:
                from core.harness.syscalls.retrieval import _rerank
                candidates = [
                    {"text": r.entry.content or r.entry.title,
                     "score": r.score}
                    for r in results
                ]
                reranked = _rerank(query.query, candidates, limit)
                reranked_ids = {(rr["text"], rr.get("score", 0)) for rr in reranked}
                results = [r for r in results
                           if (r.entry.content or r.entry.title, r.score) in reranked_ids]
                results.sort(key=lambda r: -r.score)
            except Exception as e:
                logging.debug(str(e), exc_info=True)

        return results[:limit]

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


_DEFAULT_SCORING = {
    "semantic": 0.55,
    "fts_keyword": 0.15,
    "freshness": 0.10,
    "credibility": 0.10,
    "density": 0.10,
}


def _load_scoring_weights() -> dict:
    """Load retrieval scoring weights from llm_profile.yaml. Falls back to defaults."""
    try:
        import yaml, os
        from pathlib import Path
        config_path = os.getenv("AIPLAT_LLM_CONFIG_PATH",
            str(Path(__file__).resolve().parent.parent.parent.parent.parent /
                "aiPlat-infra" / "config" / "infra" / "llm_profile.yaml"))
        profile = yaml.safe_load(open(config_path)) or {}
        cfg = profile.get("retrieval_scoring", {})
        return {
            "semantic": float(cfg.get("semantic", _DEFAULT_SCORING["semantic"])),
            "fts_keyword": float(cfg.get("fts_keyword", _DEFAULT_SCORING["fts_keyword"])),
            "freshness": float(cfg.get("freshness", _DEFAULT_SCORING["freshness"])),
            "credibility": float(cfg.get("credibility", _DEFAULT_SCORING["credibility"])),
            "density": float(cfg.get("density", _DEFAULT_SCORING["density"])),
        }
    except Exception:
        return dict(_DEFAULT_SCORING)
