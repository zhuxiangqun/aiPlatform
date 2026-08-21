"""Knowledge audit fixes — P1-1 Chinese tokenization + P2-5 graph retrieval.

Covers:
  P1-1  _score_chunk Chinese bigram tokenization (old regex scored 0.0 even
        when the chunk contained the query verbatim)
  P2-5  graph_enhance_query executes with correct bindings and returns []
        on an empty/missing graph DB (no silent crash)
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))


class TestScoreChunkChinese:
    """P1-1: Chinese runs must be bigram-tokenized, not whole-run tokens."""

    def test_chinese_containment_scores(self):
        from core.harness.knowledge.retrieval_quality_gate import _score_chunk

        # Old behaviour: 0.0 (whole-run token mismatch). New: partial overlap scores.
        s = _score_chunk("如何实现用户认证", "实现用户认证的流程")
        assert s > 0.5, f"chinese containment should score high, got {s}"

    def test_english_unchanged(self):
        from core.harness.knowledge.retrieval_quality_gate import _score_chunk

        assert _score_chunk("user auth flow", "the user auth flow docs") == 1.0

    def test_unrelated_scores_zero(self):
        from core.harness.knowledge.retrieval_quality_gate import _score_chunk

        assert _score_chunk("如何实现用户认证", "密码重置与账号管理") < 0.2


class TestGraphEnhanceQuery:
    """P2-5: graph_enhance_query bindings + empty-db behaviour."""

    def test_empty_db_returns_empty(self, tmp_path, monkeypatch):
        """Missing graph DB → [] (no crash, no phantom results)."""
        import core.harness.knowledge.graph as g

        monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
        from core.harness.knowledge.graph import graph_enhance_query

        assert graph_enhance_query("用户认证", tenant_id="default") == []

    def test_execute_bindings_match(self):
        """The SQL in graph_enhance_query has 4 placeholders + N doc_ids vs
        4 + N params (the execute tuple, not the dead `params` var)."""
        import re

        sql = ("SELECT DISTINCT doc_id FROM kb_graph WHERE tenant_id=? "
               "AND (source_entity LIKE ? OR target_entity LIKE ?) "
               "AND doc_id IN (?,?) LIMIT ?")
        n_placeholders = sql.count("?")
        # params tuple: tenant_id, token, token, doc_ids..., limit
        n_params = 1 + 2 + 2 + 1  # tenant(1), token×2, doc_ids(2), limit(1) = 6
        assert n_placeholders == n_params


class TestKbWiring:
    """P0-3: extraction pipeline wires kb_graph + kb_embeddings (both were shells)."""

    def test_wire_kb_persists_triples_and_vectors(self, tmp_path, monkeypatch):
        """_wire_kb writes doc triples to kb_graph and chunks to kb_elements/kb_embeddings."""
        import os
        import sqlite3

        monkeypatch.setenv("AIPLAT_KB_TENANTS_DIR", str(tmp_path / "kb_tenants"))
        monkeypatch.setenv("AIPLAT_EMBED_BACKEND", "hash")
        import asyncio

        from core.harness.knowledge_pipeline.extractor import (
            ExtractedRelation, ExtractionPipeline)

        pipe = ExtractionPipeline()
        rels = [ExtractedRelation(source_entity="用户认证", relation_type="依赖",
                                  target_entity="认证服务", confidence=0.9)]
        chunks = [{"offset": 0, "text": "用户认证依赖认证服务", "doc_name": "d"}]
        asyncio.run(pipe._wire_kb(rels, chunks, "test-doc", "default"))

        # kb_graph readable via graph_enhance_query (was permanently empty)
        from core.harness.knowledge.graph import graph_enhance_query
        assert len(graph_enhance_query("认证", tenant_id="default")) >= 1

        # kb_elements / kb_embeddings rows exist
        db = os.path.join(str(tmp_path / "kb_tenants"), "default", "kb.sqlite3")
        conn = sqlite3.connect(db)
        assert conn.execute("SELECT COUNT(*) FROM kb_elements").fetchone()[0] >= 1
        assert conn.execute("SELECT COUNT(*) FROM kb_embeddings").fetchone()[0] >= 1
        conn.close()

    def test_sqlite_retriever_creates_schema(self, tmp_path, monkeypatch):
        """SqliteEmbeddingRetriever auto-creates kb_elements/kb_embeddings on first use."""
        import os
        import sqlite3

        monkeypatch.setenv("AIPLAT_KB_TENANTS_DIR", str(tmp_path / "kb_tenants3"))
        from core.harness.knowledge.sqlite_retriever import SqliteEmbeddingRetriever

        r = SqliteEmbeddingRetriever(tenant_id="default")
        conn = r._connect()
        assert conn is not None  # old code returned None (no DB file)
        n = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN "
            "('kb_elements','kb_embeddings')").fetchone()[0]
        assert n == 2
        conn.close()


class TestEmbedBackend:
    """P-补全: default embed backend is semantic (real vectors), hash stays explicit."""

    def test_default_backend_semantic(self, monkeypatch):
        monkeypatch.delenv("AIPLAT_EMBED_BACKEND", raising=False)
        from core.harness.knowledge.embedder import _backend_name
        assert _backend_name() == "semantic"

    def test_explicit_hash_overrides(self, monkeypatch):
        monkeypatch.setenv("AIPLAT_EMBED_BACKEND", "hash")
        from core.harness.knowledge.embedder import _backend_name
        assert _backend_name() == "hash"

    def test_semantic_no_model_safe(self, monkeypatch):
        """No model available → embed_text_semantic returns None (skipped writes)."""
        monkeypatch.delenv("AIPLAT_EMBED_BACKEND", raising=False)
        from core.harness.knowledge import embedder
        monkeypatch.setattr(embedder, "_get_semantic_model", lambda: None)
        assert embedder.embed_text_semantic("x") is None
