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


def sys_kb_retrieve(
    query: str,
    doc_ids: List[str],
    *,
    collection_id: str = "default",
    tenant_id: str = "default",
    top_k: int = 8,
) -> List[Dict[str, Any]]:
    """Retrieve relevant text from KB documents via unified KnowledgeRetriever.

    Uses SqliteEmbeddingRetriever → KnowledgeRetriever.search() (vector + BM25 + RRF + multi-factor rerank + CRAG quality gate).

    Returns list of {text, doc_id, element_id, score, type, page_idx, start_s, end_s}.
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
        import asyncio as _asyncio
        retriever = create_sqlite_retriever(
            db_path=db_path, tenant_id=tenant_id, collection_id=collection_id,
            retrieval_strategy="hybrid", rerank_enabled=True,
            rerank_method="multi_factor", rerank_top_k=top_k * 2,
            quality_gate_enabled=True,
        )
        kb_results = _asyncio.run(retriever.search(query, limit=top_k * 2))
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
        import os as _os
        model_name = _os.getenv("AIPLAT_RERANK_MODEL", "jinaai/jina-reranker-v2-base-multilingual")
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
