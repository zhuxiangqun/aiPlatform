"""

retrieval_crag.py — Reusable CRAG 3-level retrieval chain (Phase 44).



Lifted from MaterialsChatAgent. Available to ALL RAG consumers via syscall.

CRAG chain: Level 1 ontology-first → Level 2 FTS5 → Level 3 HyDE

"""



from __future__ import annotations



import logging

from typing import Any, Dict, List, Optional, Tuple



_log = logging.getLogger("retrieval_crag")





def _boost_tables(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:

    """P0: Give table elements a priority boost in ranking.



    Table elements (type='table') get 1.2x score multiplier when sorting.

    """

    if not results:

        return results

    for r in results:

        if r.get("type") == "table":

            r["_score"] = r.get("_score", r.get("score", 1.0)) * 1.2

    results.sort(key=lambda r: r.get("_score", r.get("score", 0)), reverse=True)

    return results





async def sys_crag_retrieve(

    query: str,

    *,

    domain_id: Optional[str] = None,

    collection_id: str = "default",

    tenant_id: str = "system",

    doc_ids: Optional[List[str]] = None,

    ontology_class_uri: str = "",

    top_k: int = 8,

    enable_hyde: bool = True,

    enable_deep_research: bool = False,

    time_filters: Optional[Dict[str, int]] = None,

) -> Tuple[str, List[Dict[str, Any]]]:

    from ._trace import trace_syscall_entry

    trace_syscall_entry("sys_crag_retrieve")

    """Phase 44: Reusable CRAG 4-level retrieval chain (v2.9).



    Level 1: Ontology-first retrieval (when ontology_class_uri is known)

    Level 2: FTS5 keyword fallback (when Level 1 returns < 100 chars)

    Level 3: HyDE hypothetical answer → re-retrieve (when Level 2 returns < 50 chars)

    Level 4: Deep Research — external web search fallback (v2.9, gated by AIPLAT_DEEP_RESEARCH_ENABLED)



    Returns: (retrieved_text, citations)

    """

    retrieved_docs: str = ""

    citations: List[Dict[str, Any]] = []


    # ── Cache lookup (transparent at syscall level, v3.1) ──
    try:
        from core.harness.knowledge.semantic_cache_hook import try_cache_hit
        cache_id = collection_id if collection_id != "default" else domain_id or "default"
        cached = await try_cache_hit(query, cache_id)
        if cached:
            text = cached.get("text", "") or cached.get("llm_answer", "")
            if text and len(text) > 50:
                _log.info("Cache HIT for query in %s", cache_id)
                return text, [{"source": "semantic_cache", "text": text[:200]}]
    except Exception:
        _log.debug("Cache lookup unavailable", exc_info=True)


    # ── Cost-aware threshold (shared across ALL callers, v3.1) ──
    _effective_top_k = top_k
    try:
        from core.harness.knowledge.cost_estimator import estimate_query_cost
        cost = estimate_query_cost(query, top_k=top_k)
        if cost.complexity == "high":
            _effective_top_k = max(3, top_k // 2)
            _log.info("Cost limiter: high complexity query, top_k %d → %d", top_k, _effective_top_k)
    except Exception:
        _log.debug("cost_estimator unavailable", exc_info=True)

    # ── Level 0: GraphRAG entity routing (v3.1, shared across ALL callers) ──
    if domain_id and domain_id != "default":
        try:
            from core.harness.knowledge_pipeline.retriever import GraphRAGRetriever
            gr = GraphRAGRetriever()
            g_result = await gr.retrieve(query, domain_id=domain_id, top_k=_effective_top_k)
            if g_result.get("mode") == "graphrag" and g_result.get("chunks"):
                chunks_text = "\n\n".join(
                    f"[{c.get('title', '')}] {c.get('content', '')}"
                    for c in g_result["chunks"] if c.get("content")
                )
                paths = g_result.get("reasoning_paths", [])
                if paths:
                    chunks_text += "\n\n[关系路径]\n" + "\n".join(paths[:10])
                if chunks_text.strip():
                    retrieved_docs = chunks_text
                    citations = [{"source": f"graphrag:{domain_id}", "text": chunks_text[:200]}]
                    _log.info("GraphRAG: entity routing → %d nodes, %d chars",
                              g_result.get("subgraph_size", 0), len(retrieved_docs))
                    return retrieved_docs, citations
        except Exception:
            _log.debug("GraphRAG unavailable, falling to Level 1", exc_info=True)

    # ── Level 1: Ontology-first retrieval ──

    if ontology_class_uri:

        try:

            from core.harness.knowledge.orchestrated_retrieval import ontology_first_retrieve

            docs, cites = await ontology_first_retrieve(

                query, ontology_class_uri,

                domain_id=domain_id,

                collection_id=collection_id,

                top_k=top_k,

            )

            if docs:

                retrieved_docs = str(docs)

                citations = cites or []

        except Exception as e:

            _log.debug("ontology_first_retrieve failed: %s", e)



    # ── Level 2: FTS5 keyword fallback ──

    if not retrieved_docs or len(retrieved_docs or "") < 100:

        try:

            from core.api.facades.kb_facade import kb_retrieve

            kwargs = {}

            if time_filters:

                kwargs.update(time_filters)

            results = kb_retrieve(

                query=query,

                doc_ids=doc_ids,

                collection_id=collection_id,

                tenant_id=tenant_id,

                top_k=top_k,

                **kwargs,

            )

            if results:

                # P0: table priority boost + cells formatting

                results = _boost_tables(results)

                parts = []

                for r in results:

                    loc = ""

                    if r.get("start_s") is not None:

                        loc = f"[{r['start_s']:.0f}s] "

                    elif r.get("page_idx"):

                        loc = f"[p{r['page_idx']}] "

                    text = r.get("text", "") or ""

                    cells = r.get("cells")

                    if cells and isinstance(cells, list) and cells:

                        from core.harness.document.converters._mineru import _cells_to_markdown

                        table_text = _cells_to_markdown(cells)

                        text = f"{text}\n\n[表格]\n{table_text}" if text else f"[表格]\n{table_text}"

                    parts.append(f"{loc}{text}")

                retrieved_docs = "\n\n---\n\n".join(parts)

                citations = []

                for r in results:

                    ref = f"[doc:{r['doc_id'][:8]}]"

                    if r.get("start_s") is not None:

                        ref += f" [{r['start_s']:.0f}s-{r.get('end_s', 0):.0f}s]"

                    elif r.get("page_idx"):

                        ref += f" [p{r['page_idx']}]"

                    citations.append({"source": ref, "text": r["text"][:200]})

        except Exception as e:

            _log.debug("FTS5 fallback failed: %s", e)



    # ── Auto-compress after Level 2 (shared across ALL callers, v3.1) ──
    if retrieved_docs and len(retrieved_docs or "") > 3000:
        try:
            from core.harness.knowledge.doc_compressor import compress_retrieved_docs
            retrieved_docs = compress_retrieved_docs(retrieved_docs)
        except Exception:
            _log.debug("doc_compressor unavailable", exc_info=True)

	    # ── Level 3: HyDE reroute ──

    if enable_hyde and (not retrieved_docs or len(retrieved_docs or "") < 50):

        try:

            from core.harness.knowledge.hyde_expander import hyde_retrieve

            from core.harness.knowledge.domain_router import DomainRouter

            router = DomainRouter()

            wiki_collections = [router.resolve_collection(domain_id)] if domain_id else [collection_id] if collection_id else None

            hyde_docs, hyde_citations = await hyde_retrieve(

                query,

                wiki_collection_ids=wiki_collections,

                top_k=top_k,

            )

            if hyde_docs:

                retrieved_docs = str(hyde_docs)

                citations = hyde_citations or []

        except Exception as e:

            _log.debug("HyDE reroute failed: %s", e)



    # ── Level 4: Deep Research (v2.9) ──

    # When all internal retrieval paths fail, fall back to external web search.

    # Gated by AIPLAT_DEEP_RESEARCH_ENABLED=false by default.

    if enable_deep_research and (not retrieved_docs or len(retrieved_docs or "") < 50):

        try:

            deep_docs, deep_citations = await _deep_research_retrieve(

                query, collection_id, domain_id, top_k

            )

            if deep_docs:

                retrieved_docs = str(deep_docs)

                if deep_citations:

                    citations.extend(deep_citations)

        except Exception as e:

            _log.debug("Deep Research fallback failed: %s", e)



    return retrieved_docs, citations





async def _deep_research_retrieve(

    query: str,

    collection_id: str = "default",

    domain_id: str = "",

    top_k: int = 5,

) -> Tuple[Optional[str], List[Dict[str, Any]]]:

    """Level 4: External web search fallback when internal retrieval fails.



    Uses DuckDuckGo (no API key required) as default provider.

    Results are auto-imported into the knowledge base for future queries.

    

    Gate: AIPLAT_DEEP_RESEARCH_ENABLED must be set to 'true'.

    """

    import os as _os

    if _os.getenv("AIPLAT_DEEP_RESEARCH_ENABLED", "false").lower() not in ("true", "1", "yes"):

        return None, []



    import logging as _log

    _log.getLogger("retrieval_crag").info("Deep Research: searching web for '%s'...", query[:80])



    try:

        # DuckDuckGo search (zero-dependency, no API key)

        results = await _ddg_search(query, max_results=top_k)

        if not results:

            return None, []



        # Format results as retrievable docs

        import json as _json

        docs = []

        citations = []

        for i, r in enumerate(results[:top_k]):

            snippet = r.get("snippet", "")[:500]

            url = r.get("url", "")

            title = r.get("title", "")

            source = f"[web:{i+1}] {title} ({url})"

            docs.append(f"## {title}\n来源: {url}\n\n{snippet}")

            citations.append({

                "source": source,

                "text": snippet,

                "type": "web_search",

                "url": url,

            })



        _log.getLogger("retrieval_crag").info(

            "Deep Research: %d results found for '%s'", len(docs), query[:40])

        return "\n\n".join(docs), citations

    except Exception as e:

        _log.debug("Deep Research failed: %s", e)

        return None, []





async def _ddg_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:

    """DuckDuckGo instant answer search. Returns [{title, url, snippet}]."""

    import urllib.parse as _urlparse

    import json as _json



    try:

        import urllib.request as _urllib

        encoded = _urlparse.quote(query)

        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"

        req = _urllib.Request(url, headers={"User-Agent": "aiPlat-DeepResearch/1.0"})

        with _urllib.urlopen(req, timeout=10) as resp:

            data = _json.loads(resp.read().decode())



        results = []

        # Abstract (instant answer)

        if data.get("AbstractText"):

            results.append({

                "title": data.get("AbstractSource", "DuckDuckGo"),

                "url": data.get("AbstractURL", ""),

                "snippet": data.get("AbstractText", ""),

            })

        # Related topics

        for topic in data.get("RelatedTopics", [])[:max_results]:

            if isinstance(topic, dict) and topic.get("Text"):

                results.append({

                    "title": topic.get("FirstURL", "").split("/")[-1].replace("_", " ")[:60],

                    "url": topic.get("FirstURL", ""),

                    "snippet": topic.get("Text", ""),

                })

        return results[:max_results]

    except Exception:

        logging.getLogger(__name__).debug('_ddg_search failed', exc_info=True)


    return []

