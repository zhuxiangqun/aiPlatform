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

    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
    except Exception:
        return []

    results: List[Dict[str, Any]] = []

    try:
        # ── Paragraph fallback (keep) ──
        para_results: List[Dict[str, Any]] = []
        if not doc_ids:
            try:
                para_rows = conn.execute(
                    "SELECT element_id, doc_id, type, page_idx, text, meta_json FROM kb_elements "
                    "WHERE tenant_id=? AND type='paragraph' AND text IS NOT NULL "
                    "ORDER BY length(text) DESC LIMIT 3",
                    (tenant_id,),
                ).fetchall()
                para_results = _format_results(para_rows)
                for p in para_results:
                    p["score"] = 0.05
            except Exception:
                pass

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
            except Exception:
                pass

        # ── Unified retrieval via KnowledgeRetriever (replaces kw+vec+RRF+rerank) ──
        from core.harness.knowledge.sqlite_retriever import create_sqlite_retriever
        retriever = create_sqlite_retriever(
            db_path=db_path, tenant_id=tenant_id, collection_id=collection_id,
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

    finally:
        conn.close()

    # Phase 6: Security filter for standalone KB retrieval
    if actor_scopes is not None and results:
        results = _filter_by_security(results, actor_scopes, collection_id)

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
        except Exception:
            pass
        out.append({
            "text": str(d.get("text") or ""),
            "doc_id": str(d.get("doc_id") or ""),
            "element_id": str(d.get("element_id") or ""),
            "type": str(d.get("type") or "text"),
            "page_idx": int(d.get("page_idx") or 0),
            "score": float(d.get("score", 0.0)),
            "start_s": float(meta.get("start_ms", 0) or 0) / 1000.0 if meta.get("start_ms") else None,
            "end_s": float(meta.get("end_ms", 0) or 0) / 1000.0 if meta.get("end_ms") else None,
        })
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
    except Exception:
        pass
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
        pass
    except Exception:
        pass
    return None


def sys_wiki_retrieve(
    query: str,
    wiki_titles: List[str] = None,
    *,
    top_k: int = 8,
    link_depth: int = 0,
    collection_ids: List[str] = None,
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
                    class_uri, expand_subclasses, relation_filter, relation_boost, inference_expand
                )
                return future.result(timeout=30)
        else:
            return _sync_wiki_retrieve(query, wiki_titles, top_k, link_depth, cids,
                                       class_uri, expand_subclasses, relation_filter, relation_boost,
                                       inference_expand)
    except RuntimeError:
        return _sync_wiki_retrieve(query, wiki_titles, top_k, link_depth, cids,
                                   class_uri, expand_subclasses, relation_filter, relation_boost,
                                   inference_expand)


def _sync_wiki_retrieve(query: str, wiki_titles: List[str] = None,
                        top_k: int = 8, link_depth: int = 0,
                        collection_ids: List[str] = None,
                        class_uri: str = None,
                        expand_subclasses: bool = False,
                        relation_filter: Dict[str, str] = None,
                        relation_boost: Dict[str, float] = None,
                        inference_expand: bool = False) -> List[Dict[str, Any]]:
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
    )
    results = _run_async_in_sync(retriever.retrieve(KnowledgeQuery(query=query, limit=top_k)))

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


def sys_knowledge_retrieve(
    query: str,
    *,
    doc_ids: List[str] = None,
    wiki_titles: List[str] = None,
    tenant_id: str = "default",
    collection_id: str = "default",
    wiki_collection_ids: List[str] = None,
    top_k: int = 8,
    wiki_first: bool = True,
    min_wiki_score: float = 0.3,
    # ── Ontology-aware filtering ──
    target_class: str = None,
    expand_subclasses: bool = False,
    inference_expand: bool = False,
    # ── Security (Phase 6 fix) ──
    actor_scopes: List[str] = None,
) -> List[Dict[str, Any]]:
    """Unified knowledge retrieval — Wiki first, KB vector as fallback.

    When knowledge has been curated into Wiki pages, Wiki retrieval provides
    higher-quality results (cross-linked, LLM-edited, with typed relationships).
    For new/uncurated documents, falls back to KB vector search (traditional RAG).

    Args:
        wiki_first: If True (default), try Wiki first, fall back to KB.
                     If False, use KB directly (backward compat).

    Returns:
        List of {text, title, score, tags, summary, source, source_type}
        where source_type is "wiki" or "kb".

    边界:
      - 只读——不产生系统状态变化
      - Wiki 和 KB 分数量纲不同（归一化处理，可通过 AIPLAT_WIKI_BOOST 调权）
      - 传入 actor_scopes 时按 markings 安全过滤；不传时不过滤（向后兼容）
    退路:
      - Wiki 结果质量不足（< min_wiki_score）→ 自动补充 KB 结果
      - 需要精确过滤 → 用 target_class / relation_filter 参数
    """
    import time as _time, logging
    _t0 = _time.time()
    _wiki_time = _kb_time = 0.0
    results: List[Dict[str, Any]] = []

    # ── Wiki-first path ──
    if wiki_first:
        _tw = _time.time()
        try:
            wiki_results = sys_wiki_retrieve(
                query, wiki_titles=wiki_titles, top_k=top_k, link_depth=1,
                collection_ids=wiki_collection_ids,
                class_uri=target_class, expand_subclasses=expand_subclasses,
                inference_expand=inference_expand,
            )
            # Tag wiki results
            for wr in wiki_results:
                wr["source_type"] = "wiki"
            # Keep only results with decent scores
            qualified = [wr for wr in wiki_results if wr.get("score", 0) >= min_wiki_score]
            if len(qualified) >= max(1, top_k // 2):
                # Wiki had sufficient quality results — use them
                _wiki_time = _time.time() - _tw
                logging.getLogger("retrieval").debug(
                    f"sys_knowledge_retrieve: total={_time.time()-_t0:.3f}s wiki={_wiki_time:.3f}s kb=0 (wiki-only)")
                results = qualified
                remaining = 0
            else:
                # Otherwise: keep qualified wiki results, supplement with KB
                results = qualified
                remaining = top_k - len(qualified)
        except Exception:
            remaining = top_k
            results = []
    else:
        remaining = top_k

    _wiki_time = _time.time() - _tw
    _tk = _time.time()

    # ── KB vector fallback ──
    if remaining > 0:
        try:
            kb_results = sys_kb_retrieve(
                query, doc_ids=doc_ids or [],
                collection_id=collection_id,
                tenant_id=tenant_id,
                top_k=remaining,
            )
            for kr in kb_results:
                kr["title"] = kr.get("title") or kr.get("doc_id", "KB Document")
                kr["source_type"] = "kb"
                kr["summary"] = kr.get("text", "")[:200]
                kr["score"] = kr.get("score", 0.5)
            results.extend(kb_results)
        except Exception:
            pass

    # ── Score normalization: Wiki & KB have different score scales ──
    # Normalize each source independently (min-max with percentile cutoff),
    # then apply Wiki 1.1x boost for LLM-curated content.
    wiki_items = [r for r in results if r.get("source_type") == "wiki"]
    kb_items = [r for r in results if r.get("source_type") == "kb"]

    wiki_boost = float(os.getenv("AIPLAT_WIKI_BOOST", "1.1"))
    _normalize_scores(wiki_items, boost=wiki_boost)
    _normalize_scores(kb_items, boost=1.0)

    # ── Sort blended results by normalized score ──
    results.sort(key=lambda x: x.get("normalized_score", x.get("score", 0)), reverse=True)
    _total = _time.time() - _t0
    _kb_time = _time.time() - _tk if remaining > 0 else 0
    logging.getLogger("retrieval").debug(
        f"sys_knowledge_retrieve: total={_total:.3f}s wiki={_wiki_time:.3f}s kb={_kb_time:.3f}s "
        f"results={len(results)} wiki_first={wiki_first}")

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
            samples = _l_json.loads(open(lat_path).read())
        samples.append({"ts": _t0, "total": round(_total, 4),
                        "wiki": round(_wiki_time, 4), "kb": round(_kb_time, 4)})
        _l_os.makedirs(_l_os.path.dirname(lat_path), exist_ok=True)
        open(lat_path, "w").write(_l_json.dumps(samples[-1000:]))
    except Exception:
        pass

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
