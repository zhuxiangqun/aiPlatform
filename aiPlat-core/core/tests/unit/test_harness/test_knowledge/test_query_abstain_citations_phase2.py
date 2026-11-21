"""N21 查询 abstain+citations deepen 单元测试。"""
from __future__ import annotations

import pytest

from core.harness.knowledge_pipeline import query_abstain_citations as qac


@pytest.mark.asyncio
async def test_suite_passes_and_gate_never_certifies():
    """套件全绿且 certified / n21_full 恒 false。"""
    suite = await qac.run_query_abstain_citations_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["certified"] is False
    assert suite["n21_full_conformance"] is False
    assert suite["wiki_kb_query_entry"] is True
    assert suite["materials_graphrag_entry"] is True

    gate = qac.evaluate_query_abstain_citations_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["issues"] == []


def test_enforce_clears_abstain_citations():
    """abstain 时清空 citations/answer。"""
    out = qac.enforce_abstain_citations(
        {
            "abstained": True,
            "citations": [{"source_id": "x"}],
            "answer": "leak",
        }
    )
    assert out["citations"] == []
    assert out["answer"] == ""
    assert out["n21_enforced"] is True


def test_hit_without_citations_becomes_abstain():
    """无 citations 的命中降级为 abstain。"""
    out = qac.enforce_abstain_citations(
        {"abstained": False, "citations": [], "answer": "fake"}
    )
    assert out["abstained"] is True
    assert out["citations"] == []
    v = qac.validate_abstain_citations(out)
    assert v["ok"] is True


def test_validate_rejects_abstain_with_citations():
    """未归一化的 abstain+citations 必须失败。"""
    v = qac.validate_abstain_citations(
        {
            "abstained": True,
            "citations": [{"source_id": "x"}],
            "answer": "",
        }
    )
    assert v["ok"] is False
    assert "abstained_must_not_have_citations" in v["errors"]


def test_pack_wiki_hits_keep_citations():
    """Wiki 命中打包保留 citations。"""
    packed = qac.pack_retrieve_hits_as_query_response(
        [{"title": "P", "text": "body", "source": "wiki:P"}],
        channel="wiki",
        query="body",
    )
    out = qac.enforce_abstain_citations(packed)
    assert out["abstained"] is False
    assert out["citations"]
    assert out["channel"] == "wiki"


def test_pack_kb_orphan_hit_abstains():
    """无 source 标识的 KB 命中打包后必须 abstain。"""
    packed = qac.pack_retrieve_hits_as_query_response(
        [{"text": "orphan", "score": 0.4}],
        channel="kb",
        query="orphan",
    )
    out = qac.enforce_abstain_citations(packed)
    assert out["abstained"] is True
    assert out["citations"] == []


def test_materials_rag_without_citations_abstains():
    """MaterialsChat RAG 无引用必须 abstain。"""
    out = qac.enforce_materials_chat_output(
        {"answer": "fake", "citations": [], "strategy": "direct_retrieve"}
    )
    assert out["abstained"] is True
    assert out["n21_channel"] == "materials_chat"


def test_graphrag_envelope_attaches_n21_query():
    """GraphRAG 结果附加 n21_query 信封。"""
    out = qac.attach_graphrag_n21_envelope(
        {"mode": "vector_only", "chunks": []}, query="x"
    )
    assert out["n21_graphrag_enforced"] is True
    assert out["n21_query"]["abstained"] is True
    assert out["certified"] is False
