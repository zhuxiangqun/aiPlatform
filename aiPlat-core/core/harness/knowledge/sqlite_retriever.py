"""
SqliteEmbeddingRetriever — SQLite KB database bridge to the IRetriever interface.

Design principle (RAG unification):
  Paths 1 (sys_kb_retrieve) and 2 (intelligence/query) both read from the same
  SQLite kb_embeddings + kb_elements tables using numpy cosine similarity.
  This retriever wraps that data source in the IRetriever interface so that
  KnowledgeRetriever.search() can apply hybrid RRF, multi-factor rerank, and
  CRAG quality gate uniformly across all three retrieval paths.

Data schema (shared KB SQLite):
  kb_elements:   element_id, doc_id, type, page_idx, text, meta_json, tenant_id
  kb_embeddings: element_id, vector_json, tenant_id
"""

from __future__ import annotations

import json as _json
import logging
import os
import sqlite3
import uuid
from typing import Any, Dict, List, Optional

from .retriever import IRetriever
from .types import (
    KnowledgeEntry,
    KnowledgeMetadata,
    KnowledgeQuery,
    KnowledgeResult,
    KnowledgeSource,
    KnowledgeStatus,
    KnowledgeType,
)

_log = logging.getLogger("knowledge.sqlite_retriever")


class SqliteEmbeddingRetriever(IRetriever):
    def __init__(
        self,
        db_path: str = "",
        *,
        tenant_id: str = "default",
        collection_id: str = "default",
        domain_id: str = None,
    ):
        self._tenant_id = tenant_id
        self._collection_id = collection_id
        self._domain_id = domain_id
        if not db_path:
            root = os.path.expanduser(os.getenv("AIPLAT_KB_TENANTS_DIR", "~/.aiplat/kb/tenants"))
            db_path = os.path.join(root, tenant_id, "kb.sqlite3")
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection | None:
        if not os.path.exists(self._db_path):
            return None
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.row_factory = sqlite3.Row
            return conn
        except Exception:
            return None

    # ── IRetriever implementation ──

    async def retrieve(self, query: KnowledgeQuery) -> List[KnowledgeResult]:
        if not query.query:
            return []
        conn = self._connect()
        if not conn:
            return []
        try:
            rows = self._load_embeddings(conn, query.query, query.limit)
            if not rows:
                return []
            qvec_norm = self._embed_query(query.query)
            if qvec_norm is None:
                return []
            scored = self._cosine_score(qvec_norm, rows)
            return self._to_results(scored[: query.limit])
        except Exception:
            return []
        finally:
            conn.close()

    async def get_by_id(self, entry_id: str) -> Optional[KnowledgeEntry]:
        conn = self._connect()
        if not conn:
            return None
        try:
            row = conn.execute(
                "SELECT element_id, doc_id, type, page_idx, text, meta_json FROM kb_elements WHERE tenant_id=? AND element_id=?",
                (self._tenant_id, entry_id),
            ).fetchone()
            if not row:
                return None
            return self._row_to_entry(dict(row))
        except Exception:
            return None
        finally:
            conn.close()

    async def get_similar(self, entry: KnowledgeEntry, limit: int = 10) -> List[KnowledgeResult]:
        return await self.retrieve(KnowledgeQuery(query=entry.content, limit=limit))

    async def add(self, entry: KnowledgeEntry) -> None:
        conn = self._connect()
        if not conn:
            return
        try:
            conn.execute(
                "INSERT OR REPLACE INTO kb_elements(element_id, doc_id, type, page_idx, text, meta_json, tenant_id) VALUES(?,?,?,?,?,?,?)",
                (entry.id, "doc-0", entry.type.value, 0, entry.content, "{}", self._tenant_id),
            )
            if entry.embedding:
                conn.execute(
                    "INSERT OR REPLACE INTO kb_embeddings(element_id, vector_json, tenant_id) VALUES(?,?,?)",
                    (entry.id, _json.dumps(entry.embedding), self._tenant_id),
                )
            conn.commit()
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        finally:
            conn.close()

    async def add_batch(self, entries: List[KnowledgeEntry]) -> None:
        for e in entries:
            await self.add(e)

    # ── internal ──

    def _load_embeddings(self, conn: sqlite3.Connection, query: str, limit: int) -> list:
        try:
            query_lower = query.lower()
            keyword_terms = [w for w in query_lower.split() if len(w) >= 2]
            conditions = "WHERE emb.tenant_id = ? AND emb.vector_json IS NOT NULL AND e.text IS NOT NULL AND length(e.text) > 0"
            params: list = [self._tenant_id]
            keyword_clauses: list = []

            # KB domain pre-filter: json_extract on meta_json.domain
            if self._domain_id:
                conditions += (
                    " AND (json_extract(e.meta_json, '$.domain') = ?"
                    "      OR json_extract(e.meta_json, '$.domain') IS NULL)"
                )
                params.append(self._domain_id)

            if keyword_terms:
                keyword_clauses = ["e.text LIKE ?"] * len(keyword_terms)
                conditions += f" AND ({' OR '.join(keyword_clauses)})"
                params += [f"%{t}%" for t in keyword_terms]
            sql = f"""
                SELECT e.element_id, e.doc_id, e.type, e.page_idx, e.text, e.meta_json, emb.vector_json
                FROM kb_embeddings emb
                JOIN kb_elements e ON e.tenant_id = emb.tenant_id AND e.element_id = emb.element_id
                {conditions}
                LIMIT ?
            """
            params.append(max(limit * 5, 50))
            return conn.execute(sql, params).fetchall()
        except Exception:
            return []

    @staticmethod
    def _embed_query(query: str) -> Optional[Any]:
        try:
            from core.harness.knowledge.embedder import embed_text_semantic, hash_embed
            import numpy as np
            qvec = embed_text_semantic(query)
            if qvec is None:
                qvec = hash_embed(query)
            return np.array(qvec) / (np.linalg.norm(qvec) + 1e-8)
        except Exception:
            return None

    @staticmethod
    def _cosine_score(qvec_norm, rows) -> List[tuple]:
        import numpy as np
        scored = []
        for r in rows:
            try:
                vs = r["vector_json"]
                vec = np.array(_json.loads(vs) if isinstance(vs, str) else vs)
                vec_norm = vec / (np.linalg.norm(vec) + 1e-8)
                sim = float(np.dot(qvec_norm, vec_norm))
                if sim > 0.1:
                    scored.append((sim, dict(r)))
            except Exception:
                continue
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    def _to_results(self, scored: List[tuple]) -> List[KnowledgeResult]:
        results: List[KnowledgeResult] = []
        for score, row in scored:
            entry = self._row_to_entry(row)
            results.append(KnowledgeResult(entry=entry, score=score))
        return results

    def _row_to_entry(self, row: dict) -> KnowledgeEntry:
        return KnowledgeEntry(
            id=str(row.get("element_id", uuid.uuid4().hex)),
            type=KnowledgeType.DOCUMENT,
            content=str(row.get("text") or ""),
            title=str(row.get("doc_id") or ""),
            metadata=KnowledgeMetadata(
                source=KnowledgeSource.FILE,
                tags=[str(row.get("type", "text"))],
            ),
        )


def create_sqlite_retriever(
    db_path: str = "",
    *,
    tenant_id: str = "default",
    collection_id: str = "default",
    domain_id: str = None,
    retrieval_strategy: str = "hybrid",
    rerank_enabled: bool = True,
    rerank_method: str = "multi_factor",
    rerank_top_k: int = 5,
    quality_gate_enabled: bool = True,
    quality_threshold: float = 0.3,
) -> Any:
    """Create a KnowledgeRetriever backed by SQLite KB database."""
    from .retriever import KnowledgeRetriever

    return KnowledgeRetriever(
        retriever=SqliteEmbeddingRetriever(db_path=db_path, tenant_id=tenant_id, collection_id=collection_id, domain_id=domain_id),
        retrieval_strategy=retrieval_strategy,
        rerank_enabled=rerank_enabled,
        rerank_method=rerank_method,
        rerank_top_k=rerank_top_k,
        quality_gate_enabled=quality_gate_enabled,
        quality_threshold=quality_threshold,
    )
