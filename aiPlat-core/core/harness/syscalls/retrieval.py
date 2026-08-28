"""

sys_kb_retrieve — Core syscall for knowledge base document retrieval.



Retrieves relevant text fragments from the shared KB SQLite database.

Uses hybrid search: keyword LIKE + FTS5 full-text + vector similarity (FAISS),

fused via Reciprocal Rank Fusion (RRF).



Callers:

  - core/apps/agents/materials_chat.py (MaterialsChatAgent)

  - Any agent that needs KB document content for RAG

"""

from __future__ import annotations



import json as _json

import logging

import os

import sqlite3

from typing import Any, Dict, List, Optional, Tuple



import asyncio as _asyncio

import concurrent.futures as _cfutures





def _run_async_in_sync(coro):

    """Safely run an async coroutine from sync context.

    

    Uses asyncio.run() if no event loop is running, otherwise offloads

    to a thread pool to avoid 'cannot run event loop' crashes in uvicorn.

    """

    try:

        loop = _asyncio.get_running_loop()

        # Already in event loop → run in a fresh loop inside a thread

        with _cfutures.ThreadPoolExecutor(max_workers=1) as pool:

            return pool.submit(_asyncio.run, coro).result(timeout=120)

    except RuntimeError:

        # No running event loop → safe to use asyncio.run()

        return _asyncio.run(coro)





def sys_kb_retrieve(

    query: str,

    doc_ids: List[str],

    *,

    collection_id: str = "default",

    domain_id: str = None,

    tenant_id: str = "default",

    top_k: int = 8,

    actor_scopes: List[str] = None,

) -> List[Dict[str, Any]]:

    """Retrieve relevant text from KB documents via unified KnowledgeRetriever.



    Uses SqliteEmbeddingRetriever → KnowledgeRetriever.search() (vector + BM25 + RRF + multi-factor rerank + CRAG quality gate).



    返回: [{text, doc_id, element_id, score, type, page_idx, start_s, end_s}]



    边界:

      - 只读，不修改系统状态

      - 结果可能被截断（top_k），不能作为"不存在"的证据

      - 分数不可跨查询比较——每次检索的分数是相对的

    退路:

      - 未命中 → 扩大 top_k 或用 sys_wiki_retrieve 回退

      - 需要全文 → 用 KB 文档导出 API

    """

    if not query:

        return []



    db_path = os.path.expanduser(

        os.getenv("AIPLAT_KB_TENANTS_DIR", "~/.aiplat/kb/tenants")

    )

    db_path = os.path.join(db_path, tenant_id, "kb.sqlite3")

    if not os.path.exists(db_path):

        return []



    from core.harness.infrastructure.db_utils import get_db_connection



    with get_db_connection(db_path) as conn:

        results: List[Dict[str, Any]] = []

        # ── Paragraph fallback (keep) ──

        para_results: List[Dict[str, Any]] = []

        if not doc_ids:

            try:

                para_rows = conn.execute(

                    "SELECT element_id, doc_id, type, page_idx, text, cells_json, meta_json FROM kb_elements "

                    "WHERE tenant_id=? AND type='paragraph' AND text IS NOT NULL "

                    "ORDER BY length(text) DESC LIMIT 3",

                    (tenant_id,),

                ).fetchall()

                para_results = _format_results(para_rows)

                for p in para_results:

                    p["score"] = 0.05

            except Exception as e:

                logging.warning(str(e), exc_info=True)



        # ── Graph-enhanced document expansion (keep) ──

        if doc_ids:

            try:

                from core.harness.knowledge.graph import graph_enhance_query

                graph_docs = graph_enhance_query(query, tenant_id=tenant_id, doc_ids=doc_ids)

                expanded_ids = list(doc_ids)

                for gd in graph_docs:

                    gid = gd.get("doc_id", "")

                    if gid and gid not in expanded_ids:

                        expanded_ids.append(gid)

                if len(expanded_ids) > len(doc_ids):

                    doc_ids = expanded_ids[:max(1, len(doc_ids) + 5)]

            except Exception as e:

                logging.warning(str(e), exc_info=True)



        # ── Unified retrieval via KnowledgeRetriever (replaces kw+vec+RRF+rerank) ──

        from core.harness.knowledge.sqlite_retriever import create_sqlite_retriever

        retriever = create_sqlite_retriever(

            db_path=db_path, tenant_id=tenant_id, collection_id=collection_id,

            domain_id=domain_id,

            retrieval_strategy="hybrid", rerank_enabled=True,

            rerank_method="multi_factor", rerank_top_k=top_k * 2,

            quality_gate_enabled=True,

        )

        kb_results = _run_async_in_sync(retriever.search(query, limit=top_k * 2))

        for kr in kb_results:

            results.append({

                "text": str(kr.entry.content),

                "doc_id": str(kr.entry.title),

                "element_id": str(kr.entry.id),

                "type": "text",

                "page_idx": 0,

                "score": float(kr.score),

                "start_s": None,

                "end_s": None,

            })



        # ── FTS5 supplemental search (unique capability, keep) ──

        fts_results = _fts_search(conn, query, doc_ids, tenant_id, top_k)

        seen = {r["element_id"] for r in results}

        for f in fts_results:

            if f["element_id"] not in seen:

                results.append(f)



        # ── Paragraph fallback merge ──

        seen = {r["element_id"] for r in results}

        for p in para_results:

            if p["element_id"] not in seen:

                results.append(p)



        # ── Cross-encoder post-rerank (unique capability, keep) ──

        if len(results) > top_k:

            results = _cross_encode_rerank(query, results, top_k) or _rerank(query, results, top_k)





    # Phase 6: Security filter for standalone KB retrieval

    if actor_scopes is not None and results:

        results = _filter_by_security(results, actor_scopes, collection_id)



    # Phase 6: Provenance stale filter — exclude results from stale (outdated) sources

    if results:

        try:

            from core.harness.knowledge.provenance import get_provenance_tracker

            tracker = get_provenance_tracker()

            stale_ids = tracker.get_stale_source_ids()

            if stale_ids:

                before = len(results)

                results = [

                    r for r in results

                    if str(r.get("doc_id") or r.get("source_page") or r.get("page") or "") not in stale_ids

                ]

                if len(results) < before:

                    import logging

                    logging.getLogger("aiplat.retrieval").info(

                        f"Provenance stale filter: {before - len(results)}/{before} results excluded (stale sources)"

                    )

        except Exception as e:

            logging.warning(str(e), exc_info=True)



    # Peak-End anchoring: most relevant chunk first, second-most last

    # LLM attention decays in the middle 70% of the prompt — put

    # secondary chunks there, keep top-2 at ends (§2.2 Lost in the Middle)

    if len(results) >= 3:

        results = [results[0]] + results[2:] + [results[1]]



    return results





def _fts_search(

    conn: sqlite3.Connection,

    query: str,

    doc_ids: List[str],

    tenant_id: str,

    limit: int,

) -> List[Dict[str, Any]]:

    """FTS5 full-text search on kb_elements."""

    try:

        fts_query = " ".join(

            w for w in query.replace('"', '').replace("'", '').split()

            if len(w) >= 1

        )

        if not fts_query:

            return []



        if doc_ids:

            placeholders = ",".join(["?"] * len(doc_ids))

            doc_filter = f"AND e.doc_id IN ({placeholders})"

            params = (fts_query, tenant_id, *doc_ids, limit)

        else:

            doc_filter = ""

            params = (fts_query, tenant_id, limit)



        rows = conn.execute(

            f"""

            SELECT e.element_id, e.doc_id, e.type, e.page_idx, e.text, e.meta_json,

                   fts.rank AS score

            FROM kb_elements_fts fts

            JOIN kb_elements e ON fts.rowid = e.rowid

            WHERE kb_elements_fts MATCH ? AND e.tenant_id = ?

              AND length(e.text) >= 10

              {doc_filter}

            ORDER BY fts.rank

            LIMIT ?

            """,

            params,

        ).fetchall()



        return _format_results(rows)

    except Exception:

        return []





def _format_results(rows: list) -> List[Dict[str, Any]]:

    """Format DB rows into standardized result dicts."""

    import json as _json

    out = []

    for r in rows:

        d = dict(r)

        meta = {}

        try:

            meta = _json.loads(d.get("meta_json") or "{}")

        except Exception as e:

            logging.warning(str(e), exc_info=True)

        cells = None

        if d.get("cells_json"):

            try:

                cells = _json.loads(d["cells_json"]) if isinstance(d["cells_json"], str) else d["cells_json"]

            except Exception:

                logging.getLogger(__name__).debug('_format_results failed', exc_info=True)
        entry = {

            "text": str(d.get("text") or ""),

            "doc_id": str(d.get("doc_id") or ""),

            "element_id": str(d.get("element_id") or ""),

            "type": str(d.get("type") or "text"),

            "page_idx": int(d.get("page_idx") or 0),

            "score": float(d.get("score", 0.0)),

            "start_s": float(meta.get("start_ms", 0) or 0) / 1000.0 if meta.get("start_ms") else None,

            "end_s": float(meta.get("end_ms", 0) or 0) / 1000.0 if meta.get("end_ms") else None,

        }

        if cells is not None:

            entry["cells"] = cells

        out.append(entry)

    return out





def _cross_encode_rerank(

    query: str,

    candidates: List[Dict[str, Any]],

    top_k: int = 8,

) -> Optional[List[Dict[str, Any]]]:

    """Jina Reranker Cross-Encoder — local model, zero API cost.



    Uses InfraRerankerAdapter (unified model loading via infra).

    Returns None if model not available (falls back to rule-based rerank).

    """

    try:

        from core.harness.infrastructure.base_model_adapter import create_adapter

        adapter = create_adapter("reranker")

        return adapter.rerank(query, candidates, top_k)

    except Exception as e:

        logging.warning(str(e), exc_info=True)

    try:

        from sentence_transformers import CrossEncoder

        from core.harness.infrastructure.base_model_adapter import resolve_model_name

        model_name = resolve_model_name("reranker")

        global _ce_model, _ce_model_name

        if "_ce_model" not in dir():

            globals()["_ce_model"] = None

            globals()["_ce_model_name"] = None

        if globals().get("_ce_model_name") != model_name:

            model = CrossEncoder(model_name, max_length=512, trust_remote_code=True)

            globals()["_ce_model"] = model

            globals()["_ce_model_name"] = model_name

        else:

            model = globals()["_ce_model"]

        pairs = [(query, str(c.get("text", "")[:2000])) for c in candidates]

        scores = model.predict(pairs)

        scored = list(zip(scores, candidates))

        scored.sort(key=lambda x: x[0], reverse=True)

        result = [c for _, c in scored[:top_k]]

        for i, c in enumerate(result):

            c["score"] = float(scores[i]) if i < len(scores) else c.get("score", 0.0)

        return result

    except Exception:

        return None





def _rerank(

    query: str,

    candidates: List[Dict[str, Any]],

    top_k: int = 8,

) -> List[Dict[str, Any]]:

    """Lightweight cross-encoder style rerank.



    Scores each candidate by:

    - Token overlap density: how many query tokens appear, weighted by position

    - Length fitness: favors concise focused passages (50-500 chars optimal)

    - Exact phrase bonus: contiguous query substrings in candidate



    Zero-model, zero-API, < 1ms for typical top_n.

    """

    import re as _re



    q_lower = query.lower()

    q_tokens = _re.findall(r'[\u4e00-\u9fff]{2,4}|[a-zA-Z]{2,}', q_lower)

    q_phrases = [p for p in _re.findall(r'[\u4e00-\u9fff]{3,6}|[a-zA-Z]{4,}', q_lower) if len(p) >= 3]



    if not q_tokens:

        return candidates[:top_k]



    scored: List[Tuple[float, Dict[str, Any]]] = []

    for c in candidates:

        text = str(c.get("text", "")).lower()

        if not text:

            scored.append((c.get("score", 0.0), c))

            continue



        match_count = sum(1 for t in q_tokens if t in text)

        overlap_score = match_count / max(1, len(q_tokens))



        first_pos = len(text)

        for t in q_tokens:

            idx = text.find(t)

            if idx >= 0 and idx < first_pos:

                first_pos = idx

        pos_bonus = max(0, 0.1 - 0.1 * (first_pos / max(1, len(text)))) if first_pos < len(text) else 0.0



        phrase_bonus = 0.0

        for phrase in q_phrases:

            if phrase in text:

                phrase_bonus += 0.15



        text_len = len(text)

        if text_len < 30: len_penalty = -0.05

        elif text_len < 500: len_penalty = 0.05

        elif text_len < 2000: len_penalty = 0.0

        else: len_penalty = -0.1



        final_score = overlap_score * 0.6 + pos_bonus * 0.1 + phrase_bonus * 0.2 + len_penalty * 0.1

        scored.append((final_score, c))



    scored.sort(key=lambda x: x[0], reverse=True)

    return [c for _, c in scored[:top_k]]





def _vector_search_chroma(

    query: str,

    doc_ids: List[str],

    tenant_id: str = "default",

    limit: int = 16,

) -> Optional[List[Dict[str, Any]]]:

    """Vector search via Chroma/Milvus dedicated vector DB (optional).

    Returns None if vector DB not available (falls back to SQLite cosine).

    Configured via AIPLAT_VECTOR_DB env var."""

    backend = os.getenv("AIPLAT_VECTOR_DB", "").lower()

    if backend not in ("chroma", "milvus"):

        return None

    try:

        from core.harness.knowledge.embedder import embed_text_semantic as _embed

        qvec = _embed(query)

        if qvec is None:

            return None

        if backend == "chroma":

            import chromadb

            client = chromadb.PersistentClient(

                path=os.path.expanduser(os.getenv("AIPLAT_CHROMA_PATH", "~/.aiplat/data/chroma"))

            )

            col = client.get_or_create_collection(

                name=f"kb_{tenant_id}",

                metadata={"hnsw:space": "cosine"},

            )

            results = col.query(query_embeddings=[qvec], n_results=limit,

                                where={"doc_id": {"$in": doc_ids}} if doc_ids else None)

            if results and results.get("ids") and results["ids"][0]:

                return [{"element_id": rid, "doc_id": (results.get("metadatas") or [[{}]])[0][i].get("doc_id", ""),

                         "text": (results.get("documents") or [[""]])[0][i], "score": 1.0 - (results.get("distances") or [[1.0]])[0][i]}

                        for i, rid in enumerate(results["ids"][0])]

    except ImportError:

        pass  # noqa: optional-dependency

    except Exception as e:

        logging.warning(str(e), exc_info=True)

    return None





def sys_wiki_retrieve(

    query: str,

    wiki_titles: List[str] = None,

    *,

    top_k: int = 8,

    link_depth: int = 0,

    collection_ids: List[str] = None,

    tenant_id: str = "",

    # ── Ontology-aware filtering ──

    class_uri: str = None,

    expand_subclasses: bool = False,

    relation_filter: Dict[str, str] = None,

    relation_boost: Dict[str, float] = None,

    inference_expand: bool = True,

) -> List[Dict[str, Any]]:

    u"""Retrieve relevant text from wiki knowledge pages via semantic embedding.



    Uses WikiPageRetriever → embed_text_semantic() → InfraEmbeddingAdapter → infra ModelManager.



    Args:

        collection_ids: Wiki collections to search. Defaults to ["default"].

        tenant_id: Optional tenant scoping for multi-tenant deployments.

        class_uri: Filter pages to those belonging to this T-Box class.

        expand_subclasses: Recursively include subclass pages.

        relation_filter: Only return pages related to target via relation_type.

        relation_boost: Boost scores for pages with specific relation types.



    返回: [{text, title, score, tags, summary, source}]



    边界:

      - 只读，不修改系统状态

      - 受 inference_cache.json 缓存控制——新建页面最多 300 秒延迟

      - 分数不可跨查询比较

    退路:

      - 未命中 → sys_kb_retrieve 做文档级回退

      - 结果太多 → 缩小 collection_ids 范围

    """

    from core.harness.knowledge.wiki_retriever import WikiPageRetriever



    cids = collection_ids or ["default"]

    # Default: cite/parent/support relations get positive boost

    default_boost = relation_boost if relation_boost is not None else {

        "cites": 0.3, "supports": 0.2, "parent": 0.15, "extends": 0.1

    }

    retriever = WikiPageRetriever(

        wiki_titles=wiki_titles or [],

        link_depth=link_depth,

        collection_ids=cids,

        class_uri=class_uri,

        expand_subclasses=expand_subclasses,

        relation_filter=relation_filter,

        relation_boost=default_boost,

        inference_expand=inference_expand,

    )

    import asyncio

    try:

        loop = asyncio.get_event_loop()

        if loop.is_running():

            # In async context, use a thread pool to run sync retrieval

            with _cfutures.ThreadPoolExecutor(max_workers=1) as executor:

                future = executor.submit(

                    _sync_wiki_retrieve, query, wiki_titles, top_k, link_depth, cids,

                    class_uri, expand_subclasses, relation_filter, relation_boost, inference_expand,

                    tenant_id

                )

                return future.result(timeout=30)

        else:

            return _sync_wiki_retrieve(query, wiki_titles, top_k, link_depth, cids,

                                       class_uri, expand_subclasses, relation_filter, relation_boost,

                                       inference_expand, tenant_id)

    except RuntimeError:

        return _sync_wiki_retrieve(query, wiki_titles, top_k, link_depth, cids,

                                   class_uri, expand_subclasses, relation_filter, relation_boost,

                                   inference_expand, tenant_id)





def _sync_wiki_retrieve(query: str, wiki_titles: List[str] = None,

                        top_k: int = 8, link_depth: int = 0,

                        collection_ids: List[str] = None,

                        class_uri: str = None,

                        expand_subclasses: bool = False,

                        relation_filter: Dict[str, str] = None,

                        relation_boost: Dict[str, float] = None,

                        inference_expand: bool = False,

                        tenant_id: str = "") -> List[Dict[str, Any]]:

    from core.harness.knowledge.wiki_retriever import WikiPageRetriever

    from core.harness.knowledge.types import KnowledgeQuery



    cids = collection_ids or ["default"]

    default_boost2 = relation_boost if relation_boost is not None else {

        "cites": 0.3, "supports": 0.2, "parent": 0.15, "extends": 0.1

    }

    retriever = WikiPageRetriever(

        wiki_titles=wiki_titles or [], link_depth=link_depth,

        collection_ids=cids,

        class_uri=class_uri, expand_subclasses=expand_subclasses,

        relation_filter=relation_filter, relation_boost=default_boost2,

        inference_expand=inference_expand,

        tenant_id=tenant_id,

    )

    results = _run_async_in_sync(retriever.retrieve(KnowledgeQuery(query=query, limit=top_k, tenant_id=tenant_id)))



    return [

        {

            "text": r.entry.content,

            "title": r.entry.title,

            "score": r.score,

            "tags": r.entry.metadata.tags,

            "summary": r.entry.summary or r.highlight or "",

            "source": r.entry.references,

        }

        for r in results

    ]





class WikiCircuitBreaker:

    u"""Circuit breaker for Wiki retrieval — prevents cascading failures.



    Isolated per (domain_id, tenant_id) using BaseCircuitBreaker instances

    to prevent one tenant's failure from affecting others.

    """

    

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 60.0):

        import threading

        from core.harness.infrastructure.circuit_breaker import BaseCircuitBreaker

        self.failure_threshold = failure_threshold

        self.recovery_timeout = recovery_timeout

        self._lock = threading.Lock()

        self._breakers: dict = {}



    def _get(self, domain_id: str = "default", tenant_id: str = "default"):

        from core.harness.infrastructure.circuit_breaker import BaseCircuitBreaker

        key = f"{domain_id}:{tenant_id}"

        with self._lock:

            if key not in self._breakers:

                self._breakers[key] = BaseCircuitBreaker(

                    failure_threshold=self.failure_threshold,

                    recovery_timeout=self.recovery_timeout,

                    name=f"wiki:{key}",

                )

            return self._breakers[key]



    def allow_request(self, domain_id: str = "default", tenant_id: str = "default") -> bool:

        return self._get(domain_id, tenant_id).allow()



    def record_success(self, domain_id: str = "default", tenant_id: str = "default"):

        self._get(domain_id, tenant_id).success()



    def record_failure(self, domain_id: str = "default", tenant_id: str = "default"):

        self._get(domain_id, tenant_id).failure()





# Global wiki circuit breaker — isolated per (domain, tenant)

_wiki_circuit_breaker = WikiCircuitBreaker(failure_threshold=3, recovery_timeout=60.0)





def sys_knowledge_retrieve(

    query: str,

    *,

    doc_ids: List[str] = None,

    wiki_titles: List[str] = None,

    tenant_id: str = "default",

    collection_id: str = "default",

    wiki_collection_ids: List[str] = None,

    domain_id: str = None,

    top_k: int = 8,

    wiki_first: bool = True,

    min_wiki_score: float = 0.3,

    # ── Ontology-aware filtering ──

    target_class: str = None,

    expand_subclasses: bool = False,

    # ── RAG Phase: latency tracking ──

    _track_latency: bool = True,



    inference_expand: bool = False,

    # ── Security (Phase 6 fix) ──

    actor_scopes: List[str] = None,

) -> List[Dict[str, Any]]:

    """Unified knowledge retrieval — parallel Wiki + KB via RRF fusion.



    Executes Wiki and KB queries in parallel, then fuses results using

    Reciprocal Rank Fusion (RRF). GraphIndex high-confidence Early Exit

    supported when available.



    Args:

        wiki_first: If True (default), run Wiki + KB in parallel with RRF fusion.

                     If False, use KB directly (backward compat).



    Returns:

        List of {text, title, score, tags, summary, source, source_type}

        where source_type is "wiki" or "kb".

    """

    import time as _time, logging, concurrent.futures

    _t0 = _time.time()

    results: List[Dict[str, Any]] = []



    if not wiki_first:

        # Backward-compat: KB-only path

        try:

            results = sys_kb_retrieve(

                query, doc_ids=doc_ids or [],

                collection_id=collection_id, domain_id=domain_id,

                tenant_id=tenant_id, top_k=top_k,

            )

            for kr in results:

                kr["title"] = kr.get("title") or kr.get("doc_id", "KB Document")

                kr["source_type"] = "kb"

                kr["summary"] = kr.get("text", "")[:200]

                kr["score"] = kr.get("score", 0.5)

        except Exception:

            logging.getLogger("retrieval").warning(

                "sys_knowledge_retrieve KB-only path failed", exc_info=True)

        _total = _time.time() - _t0

        logging.getLogger("retrieval").debug(

            f"sys_knowledge_retrieve: total={_total:.3f}s kb-only results={len(results)}")

        return results



    # ── Parallel Wiki + KB retrieval ──

    wiki_results: List[Dict[str, Any]] = []

    kb_results: List[Dict[str, Any]] = []



    def _fetch_wiki():

        if not _wiki_circuit_breaker.allow_request(

            domain_id=domain_id or "default", tenant_id=tenant_id or "default"):

            return []

        try:

            out = sys_wiki_retrieve(

                query, wiki_titles=wiki_titles, top_k=max(top_k, 10), link_depth=1,

                collection_ids=wiki_collection_ids,

                tenant_id=tenant_id,

                class_uri=target_class, expand_subclasses=expand_subclasses,

                inference_expand=inference_expand,

            )

            _wiki_circuit_breaker.record_success(

                domain_id=domain_id or "default", tenant_id=tenant_id or "default")

            for wr in out:

                wr["source_type"] = "wiki"

            return out

        except Exception:

            _wiki_circuit_breaker.record_failure(

                domain_id=domain_id or "default", tenant_id=tenant_id or "default")

            logging.getLogger("retrieval").warning(

                "sys_knowledge_retrieve: wiki retrieval failed", exc_info=True)

            return []



    def _fetch_kb():

        try:

            out = sys_kb_retrieve(

                query, doc_ids=doc_ids or [],

                collection_id=collection_id, domain_id=domain_id,

                tenant_id=tenant_id, top_k=max(top_k, 10),

            )

            for kr in out:

                kr["title"] = kr.get("title") or kr.get("doc_id", "KB Document")

                kr["source_type"] = "kb"

                kr["summary"] = kr.get("text", "")[:200]

                kr["score"] = kr.get("score", 0.5)

            return out

        except Exception:

            logging.getLogger("retrieval").warning(

                "sys_knowledge_retrieve KB fetch failed", exc_info=True)

            return []



    # ── Execute Wiki + KB in parallel ──

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:

        wiki_future = pool.submit(_fetch_wiki)

        kb_future = pool.submit(_fetch_kb)

        wiki_results = wiki_future.result(timeout=30)

        kb_results = kb_future.result(timeout=30)



    # ── GraphIndex Early Exit (when available) ──

    graph_early_exit = False

    try:

        from core.harness.ontology_engine.graph_index import GraphIndex

        gi = GraphIndex(domain_id=domain_id or "default")

        if hasattr(gi, 'traverse') and gi._entities:

            g_results = gi.traverse(query, max_depth=2, top_k=3)

            if g_results and g_results[0].get("confidence", 0) > 0.92:

                graph_early_exit = True

                results = [{

                    "text": str(g_results[0].get("description", g_results[0].get("name", ""))),

                    "title": str(g_results[0].get("name", "Graph Entity")),

                    "score": float(g_results[0].get("confidence", 0.95)),

                    "source_type": "graph",

                    "summary": str(g_results[0].get("description", ""))[:200],

                    "tags": g_results[0].get("tags", []),

                    "source": "graph_index",

                }]

    except Exception as e:

        logging.warning(str(e), exc_info=True)



    if graph_early_exit:

        _total = _time.time() - _t0

        try:

            from core.harness.memory.metrics import inc_early_exit

            inc_early_exit("graph")

        except Exception as e:

            logging.warning(str(e), exc_info=True)

        logging.getLogger("retrieval").debug(

            f"sys_knowledge_retrieve: total={_total:.3f}s graph-early-exit results={len(results)}")

        return results



    # ── RRF Fusion: merge Wiki + KB results ──

    if wiki_results or kb_results:

        try:

            # True Reciprocal Rank Fusion: key by document identity (normalized title) so a

            # document appearing in BOTH the Wiki and KB ranked lists has its reciprocal-rank

            # contributions SUMMED (cross-source relevance boost) and is deduplicated to a single

            # entry — rather than keyed by (source, position), which never fused across sources.

            rrf_k = 60

            scores: Dict[str, float] = {}

            items: Dict[str, Any] = {}

            wiki_boost = float(os.getenv("AIPLAT_WIKI_BOOST", "1.1"))



            def _doc_key(it: Dict[str, Any], source: str, idx: int) -> str:

                t = str(it.get("title") or "").strip().lower()

                return t or f"__{source}_{idx}__"



            for rank, item in enumerate(wiki_results):

                key = _doc_key(item, "wiki", rank)

                scores[key] = scores.get(key, 0.0) + wiki_boost / (rrf_k + rank + 1)

                items.setdefault(key, item)

            for rank, item in enumerate(kb_results):

                key = _doc_key(item, "kb", rank)

                scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank + 1)

                items.setdefault(key, item)



            ranked = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)

            results = [items[k] for k in ranked[:top_k * 2]]



            # v2.9: Authority boost — authoritative sources always appear first

            authoritative = [r for r in results if r.get("source_priority", 0) >= 8]

            normal = [r for r in results if r.get("source_priority", 0) < 8]

            results = authoritative + normal



            # Carry the fused RRF score (drives final ordering below).

            for k in ranked[:len(results)]:

                items[k]["rrf_score"] = scores[k]

        except Exception:

            # Fallback: simple concatenation

            results = wiki_results + kb_results



    # ── Score normalization ──

    wiki_items = [r for r in results if r.get("source_type") == "wiki"]

    kb_items = [r for r in results if r.get("source_type") == "kb"]

    wiki_boost_norm = float(os.getenv("AIPLAT_WIKI_BOOST", "1.1"))

    _normalize_scores(wiki_items, boost=wiki_boost_norm)

    _normalize_scores(kb_items, boost=1.0)



    # ── Sort blended results: fused RRF score drives order, normalized score tie-breaks ──

    results.sort(

        key=lambda x: (x.get("rrf_score", 0.0), x.get("normalized_score", x.get("score", 0))),

        reverse=True,

    )

    _total = _time.time() - _t0

    try:

        from core.harness.memory.metrics import observe_rrf_latency

        observe_rrf_latency(_total)

    except Exception as e:

        logging.warning(str(e), exc_info=True)

    logging.getLogger("retrieval").debug(

        f"sys_knowledge_retrieve: total={_total:.3f}s rrf-fused results={len(results)}")



    # ── Post-Retrieval Governance ──

    try:

        from core.harness.knowledge.post_retrieval_governor import PostRetrievalGovernor

        cid = wiki_collection_ids[0] if wiki_collection_ids else "default"

        governor = PostRetrievalGovernor()

        governed, gov_hints, gov_stats = governor.govern(results[:top_k * 2], query, cid)

        if governed:

            # Embed governance flag + stats in the first chunk (lists don't support attributes)

            governed[0]["_governance_applied"] = True

            governed[0]["_governance_stats"] = {

                "raw": gov_stats.raw_count, "governed": gov_stats.governed_count,

                "time_penalized": gov_stats.time_penalized,

                "density_filtered": gov_stats.density_filtered,

                "dedup_merged": gov_stats.dedup_merged,

                "conflict_marked": gov_stats.conflict_marked,

                "avg_composite": gov_stats.avg_composite_score,

            }

            governed[0]["_governance_hints"] = {

                "has_conflicts": gov_hints.has_conflicts,

                "conflict_pairs": gov_hints.conflict_pairs[:5],

                "oldest_source_age": gov_hints.oldest_source_age,

                "applied": gov_hints.governance_applied,

            }

            results = governed

            logging.getLogger("retrieval").debug(

                f"PostRetrievalGovernor: {gov_stats.raw_count}→{gov_stats.governed_count} "

                f"time_pen={gov_stats.time_penalized} dedup={gov_stats.dedup_merged} "

                f"cutoff={gov_stats.cutoff_score:.3f} avg={gov_stats.avg_composite_score:.3f}")

    except Exception:

        logging.getLogger("retrieval").debug("PostRetrievalGovernor skipped", exc_info=True)



    # ── Phase 6: Security filter ──

    if actor_scopes is not None:

        results = _filter_by_security(results, actor_scopes, collection_id)



    # ── Latency tracking ──

    try:

        import os as _l_os, json as _l_json

        lat_path = _l_os.path.join(

            _l_os.path.expanduser(_l_os.getenv("AIPLAT_HOME", "~/.aiplat")),

            "wiki", "retrieval_latency.json")

        samples = []

        if _l_os.path.exists(lat_path):
            try:
                samples = _l_json.loads(open(lat_path).read())
            except Exception:
                samples = []  # noqa: corrupt-file-recovery

        samples.append({"ts": _t0, "total": round(_total, 4),

                        "wiki": round(_total, 4), "kb": round(_total, 4)})  # noqa: F821

        _l_os.makedirs(_l_os.path.dirname(lat_path), exist_ok=True)

        open(lat_path, "w").write(_l_json.dumps(samples[-1000:]))

    except Exception as e:

        logging.warning(str(e), exc_info=True)



    # Phase C6: record to centralized latency aggregator

    try:

        from core.harness.knowledge.cost_estimator import record_latency as _rec_lat

        _rec_lat("rag", (_time.time() - _t0) * 1000)

    except Exception:

        logging.getLogger(__name__).debug('code failed', exc_info=True)


    # Phase 47: KnowledgeROI auto-recording (best-effort)
    try:
        from core.harness.knowledge.knowledge_roi import KnowledgeROI

        # Estimate tokens: ~500 per wiki page + ~300 per kb doc
        rag_tokens = len(results) * 500
        wiki_tokens = max(50, rag_tokens // 8)  # Wiki mode uses ~1/8 of RAG tokens

        roi = KnowledgeROI()
        roi.record_from_syscall(
            query_text=query[:200],
            domain_id=domain_id or collection_id or "default",
            rag_tokens=rag_tokens,
            wiki_tokens=wiki_tokens,
            cache_hit=bool(graph_early_exit),
        )
    except Exception:
        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

    return results[:top_k]





def _filter_by_security(

    results: List[Dict[str, Any]],

    actor_scopes: List[str],

    collection_id: str = "default",

) -> List[Dict[str, Any]]:

    u"""Filter blended retrieval results by markings + per-object permissions.



    Applied at the unified entry (sys_knowledge_retrieve) after blending

    Wiki and KB results. Admin scope bypasses all restrictions.



    Each result is checked against:

      1. Markings (lineage-based confidentiality labels)

      2. Per-object access (RBAC fine-grained permission)

    """

    if not results or actor_scopes is None or "admin" in actor_scopes:

        return results



    try:

        from core.harness.knowledge.knowledge_markings import (

            load_markings_config, resolve_effective_markings, MarkingLevel,

        )

        from core.harness.knowledge.knowledge_abox_builder import _safe_uri

        from core.harness.knowledge.knowledge_ontology import get_ontology



        AI = "http://aiplat.local/knowledge#"

        marking_config = load_markings_config(collection_id)

        onto = get_ontology()



        filtered = []

        for r in results:

            title = r.get("title", "")

            if not title:

                filtered.append(r)

                continue



            entity_uri = r.get("_entity_uri") or f"{AI}{_safe_uri(title)}"



            # Check markings

            effective, _ = resolve_effective_markings(

                entity_uri, marking_config, onto.triples, max_depth=3,

            )

            blocked = False

            for m in effective:

                if m.level >= MarkingLevel.INTERNAL:

                    required_scope = m.scope or f"kb:read:{m.label.lower()}"

                    if required_scope not in set(actor_scopes):

                        blocked = True

                        break



            if not blocked:

                filtered.append(r)



        return filtered

    except Exception:

        return results  # best-effort: allow all on filter failure





def _normalize_scores(

    results: List[Dict[str, Any]],

    *,

    boost: float = 1.0,

    percentile_cutoff: int = 2,

) -> None:

    u"""Min-max normalize scores within a group, with percentile cutoff.



    Percentile cutoff reduces sensitivity to outliers:

      - 2% cutoff: a single extremely low score won't pull the denominator down

      - 0% cutoff: standard min-max (all scores included)



    Applies a multiplicative boost after normalization.

    Modifies results in-place, adding 'normalized_score' field.



    If all scores identical (min == max), assigns 0.5 uniformly.

    """

    if not results:

        return



    try:

        scores = [r.get("score", 0.0) for r in results]

        min_s = min(scores)

        max_s = max(scores)



        # Percentile cutoff: exclude top/bottom percentiles from min/max

        if len(scores) >= 5 and percentile_cutoff > 0:

            import math

            idx_lo = max(0, math.ceil(len(scores) * percentile_cutoff / 100) - 1)

            idx_hi = min(len(scores) - 1, math.floor(len(scores) * (100 - percentile_cutoff) / 100))

            sorted_scores = sorted(scores)

            min_s = min(min_s, sorted_scores[idx_lo])

            max_s = max(max_s, sorted_scores[idx_hi])



        if max_s <= min_s:

            for r in results:

                r["normalized_score"] = 0.5

            return



        for r in results:

            raw = r.get("score", 0.0)

            norm = (raw - min_s) / (max_s - min_s)

            norm = max(0.0, min(1.0, norm))

            r["normalized_score"] = round(norm * boost, 4)

    except Exception:

        # Fallback: use raw score

        for r in results:

            r["normalized_score"] = r.get("score", 0.0)



# ════════════════════════════════════════════════════════════════
# 意图路由统一检索（AnySearch 借鉴 P0-2，2026-08-28）
# 查询理解驱动：先判定查询意图（代码/知识/通用事实），路由到匹配通道，
# 避免全域盲搜（对齐"查询理解驱动智能路由"理念）。
# ════════════════════════════════════════════════════════════════

# 代码意图特征（关键词子串匹配，轻量 T1；不涉及业务域语义）
_CODE_INTENT_HINTS = (
    "python", "javascript", "typescript", "java", "golang", "rust",
    "函数", "类", "模块", "报错", "异常", "bug", "api", "sdk",
    "代码", "实现", "算法", "重构", "依赖", "库",
)

# 知识库意图特征（内部文档/专业术语倾向）
_KB_INTENT_HINTS = (
    "手册", "文档", "wiki", "规范", "标准", "流程", "制度",
    "指南", "说明", "操作", "配置", "术语", "域",
)


def _route_intent(query: str) -> str:
    """轻量意图判定：返回 code / knowledge / web（T1 关键词，无 LLM 依赖）。

    判定优先级：代码特征 > 知识库特征 > 通用 web。
    避免对业务域语义做推断（仅检索通道选择，不涉及业务概念）。
    """
    q = (query or "").lower()
    code_hits = sum(1 for h in _CODE_INTENT_HINTS if h in q)
    kb_hits = sum(1 for h in _KB_INTENT_HINTS if h in q)
    if code_hits >= 1 and code_hits >= kb_hits:
        return "code"
    if kb_hits >= 2:
        return "knowledge"
    return "web"


async def sys_routed_retrieve(query: str, *, top_k: int = 8, include_web: bool = True,
                              tenant_id: str = "default", collection_id: str = "default",
                              doc_ids: List[str] = None) -> Dict[str, Any]:
    """意图路由统一检索：code/knowledge/web 三通道按查询意图分发。

    返回 {route, results, sources}：
      route    — 实际路由的通道（code/knowledge/web）
      results  — 通道结果（统一为 {text, score, source} 事实条目形态）
      sources  — 信源标注数组（source/url/text，对齐 web_search 结构化输出）

    安全边界：
      - 只读，不修改系统状态
      - web 通道仅在 include_web=True 时启用（默认开，供 Agent 外部信息感知）
      - 通道选择是"检索类型"判定，不推断业务域语义（§5.29 合规）
    """
    intent = _route_intent(query)
    results: List[Dict[str, Any]] = []
    sources: List[Dict[str, Any]] = []

    if intent == "code":
        try:
            from core.harness.syscalls.code import sys_code_search
            resp = await sys_code_search(query, max_results=top_k)
            hits = (resp.get("results") or []) if isinstance(resp, dict) else (resp or [])
            for h in hits:
                if not isinstance(h, dict):
                    continue
                text = str(h.get("content") or h.get("text") or h.get("path") or "")
                if not text:
                    continue
                results.append({"text": text[:800], "score": float(h.get("score", 0) or 0),
                                "source": "code"})
                sources.append({"source": "code", "url": str(h.get("path") or ""),
                                "text": text[:300]})
        except Exception:
            intent = "knowledge"  # 代码检索不可用 → 降级知识通道

    if intent == "knowledge":
        try:
            hits = sys_knowledge_retrieve(
                query, doc_ids=doc_ids, tenant_id=tenant_id,
                collection_id=collection_id, top_k=top_k)
            for h in hits or []:
                if not isinstance(h, dict):
                    continue
                text = str(h.get("text") or "")
                if not text:
                    continue
                results.append({"text": text[:800], "score": float(h.get("score", 0) or 0),
                                "source": "knowledge"})
                sources.append({"source": "knowledge", "url": str(h.get("doc_id") or ""),
                                "text": text[:300]})
        except Exception:
            intent = "web"  # 知识检索不可用 → 降级 web

    if intent == "web" and include_web:
        try:
            # 合规：harness 层不 import apps 层（§5.14 分层边界）。
            # 直接 urllib 调 DuckDuckGo JSON Instant Answer（对齐 retrieval_crag._ddg_search 模式），
            # 本地归一化为结构化事实条目（信源标注 + 多源去重）。
            import urllib.parse as _urlparse
            import urllib.request as _urlreq
            import json as _json

            _url = f"https://api.duckduckgo.com/?q={_urlparse.quote(query)}&format=json&no_html=1"
            _req = _urlreq.Request(_url, headers={"User-Agent": "Mozilla/5.0"})
            with _urlreq.urlopen(_req, timeout=15) as _resp:
                _data = _json.loads(_resp.read().decode("utf-8", errors="ignore"))
            _seen: set = set()
            if _data.get("Abstract"):
                _u = str(_data.get("AbstractURL") or "").strip()
                if _u and _u not in _seen:
                    _seen.add(_u)
                    results.append({"text": str(_data.get("Abstract") or "")[:800],
                                   "score": 0.7, "source": "ddg_abstract"})
                    sources.append({"source": "ddg_abstract", "url": _u,
                                   "text": str(_data.get("Abstract") or "")[:300]})
            for _topic in _data.get("RelatedTopics", [])[:top_k]:
                if not isinstance(_topic, dict) or not _topic.get("Text"):
                    continue
                _u = str(_topic.get("FirstURL") or "").strip()
                if not _u or _u in _seen:
                    continue
                _seen.add(_u)
                results.append({"text": str(_topic.get("Text") or "")[:800],
                               "score": 0.5, "source": "ddg_related"})
                sources.append({"source": "ddg_related", "url": _u,
                               "text": str(_topic.get("Text") or "")[:300]})
        except Exception:
            pass  # noqa: cleanup-best-effort — web 不可用则返回空结果（不伪装命中）

    return {"route": intent, "results": results[:top_k], "sources": sources[:top_k]}
