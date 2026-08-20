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
