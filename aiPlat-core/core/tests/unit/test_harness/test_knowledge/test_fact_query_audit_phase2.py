"""N19 Fact/Query 统一审计 deepen 单元测试。"""
from __future__ import annotations

import pytest

from core.harness.knowledge_pipeline import fact_query_audit as fqa


def test_suite_passes_and_gate_never_certifies():
    """套件全绿且 certified / n19_full 恒 false；含热路径入口门。"""
    suite = fqa.run_fact_query_audit_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["certified"] is False
    assert suite["n19_full_conformance"] is False
    ids = {c["id"] for c in suite["cases"]}
    assert "put_fact_hotpath_entry" in ids
    assert "query_gateway_hotpath_entry" in ids
    assert "query_facts_gateway_hotpath_entry" in ids
    assert "query_facts_list_hotpath_entry" in ids
    assert "materials_chat_hotpath_entry" in ids
    assert "graphrag_hotpath_entry" in ids
    assert "wiki_kb_hotpath_entry" in ids
    assert "bare_list_hotpath_entry" in ids
    assert "kb_qa_hotpath_entry" in ids
    assert "knowledge_retrieve_hotpath_entry" in ids
    assert "wiki_context_hotpath_entry" in ids
    assert "wiki_structured_hotpath_entry" in ids
    assert "ontology_context_hotpath_entry" in ids
    assert "ontology_urn_hotpath_entry" in ids
    assert "wiki_pages_hotpath_entry" in ids
    assert "graph_neighbors_hotpath_entry" in ids
    assert "graph_query_hotpath_entry" in ids
    assert "hotpath_helper_writes" in ids

    gate = fqa.evaluate_fact_query_audit_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["n19_full_conformance"] is False
    assert gate["issues"] == []


def test_hotpath_helper_writes_and_env_off(tmp_path, monkeypatch):
    """热路径 helper 可写；AIPLAT_FACT_QUERY_AUDIT_HOTPATH=0 时跳过。"""
    db = str(tmp_path / "fqa.sqlite3")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_HOTPATH", "1")
    hit = fqa.maybe_record_hotpath_audit(
        tenant_id="t-hp",
        kind="query",
        subject_ref="q-hp",
        after_snapshot={"abstained": True, "citations": []},
        runtime_authority="query_gateway",
        db_path=db,
    )
    assert hit and hit.get("snapshot_id")
    assert (hit.get("meta") or {}).get("hotpath") is True

    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_HOTPATH", "0")
    assert fqa.hotpath_audit_enabled() is False
    skip = fqa.maybe_record_hotpath_audit(
        tenant_id="t-hp",
        kind="query",
        subject_ref="q-skip",
        after_snapshot={"abstained": True, "citations": []},
        runtime_authority="query_gateway",
        db_path=db,
    )
    assert skip is None
    listed = fqa.list_audit_snapshots(tenant_id="t-hp", db_path=db)
    assert listed["count"] == 1


def test_materials_chat_hotpath_writes(tmp_path, monkeypatch):
    """MaterialsChat 直出热路径落 Query 快照；空 tenant 跳过。"""
    db = str(tmp_path / "fqa-mc.sqlite3")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_HOTPATH", "1")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_DB", db)
    out = fqa.maybe_record_materials_chat_hotpath(
        tenant_id="t-mc",
        output={
            "answer": "ok",
            "citations": [{"source_id": "s1"}],
            "abstained": False,
            "n21_enforced": True,
            "gateway_f1": {"abstained": False},
        },
        exit_kind="rag",
        query="q?",
        db_path=db,
    )
    assert out.get("answer") == "ok"
    listed = fqa.list_audit_snapshots(tenant_id="t-mc", db_path=db)
    assert listed["count"] == 1
    item = listed["items"][0]
    assert item["runtime_authority"] == "materials_chat"
    assert (item.get("meta") or {}).get("op") == "materials_chat"
    assert (item.get("after_snapshot") or {}).get("has_gateway_f1") is True

    skipped = fqa.maybe_record_materials_chat_hotpath(
        tenant_id="",
        output={"answer": "x", "citations": [], "abstained": True},
        exit_kind="shortcut",
        db_path=db,
    )
    assert skipped.get("answer") == "x"
    assert fqa.list_audit_snapshots(tenant_id="t-mc", db_path=db)["count"] == 1


def test_graphrag_hotpath_writes(tmp_path, monkeypatch):
    """GraphRAG 旁路热路径落 Query 快照；空 tenant 跳过。"""
    db = str(tmp_path / "fqa-gr.sqlite3")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_HOTPATH", "1")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_DB", db)
    out = fqa.maybe_record_graphrag_hotpath(
        tenant_id="t-gr",
        result={
            "mode": "graphrag",
            "chunks": [{"title": "c1", "content": "hit", "source": "d1"}],
            "n21_query": {
                "abstained": False,
                "citations": [{"source_id": "d1"}],
                "answer": "a",
            },
            "n21_graphrag_enforced": True,
            "gateway_f1": {"abstained": False},
        },
        query="graph?",
        db_path=db,
    )
    assert out.get("mode") == "graphrag"
    listed = fqa.list_audit_snapshots(tenant_id="t-gr", db_path=db)
    assert listed["count"] == 1
    item = listed["items"][0]
    assert item["runtime_authority"] == "graphrag"
    assert (item.get("meta") or {}).get("op") == "graphrag_retrieve"
    assert (item.get("after_snapshot") or {}).get("n21_graphrag_enforced") is True

    skipped = fqa.maybe_record_graphrag_hotpath(
        tenant_id="",
        result={"mode": "vector_only", "chunks": []},
        db_path=db,
    )
    assert skipped.get("mode") == "vector_only"
    assert fqa.list_audit_snapshots(tenant_id="t-gr", db_path=db)["count"] == 1


def test_wiki_kb_hotpath_writes(tmp_path, monkeypatch):
    """Wiki/KB 旁路热路径落 Query 快照；空 tenant 跳过。"""
    db = str(tmp_path / "fqa-wk.sqlite3")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_HOTPATH", "1")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_DB", db)
    out = fqa.maybe_record_wiki_kb_hotpath(
        tenant_id="t-wk",
        response={
            "answer": "w",
            "citations": [{"source_id": "w1"}],
            "abstained": False,
            "n21_query": {"abstained": False, "citations": [{"source_id": "w1"}]},
        },
        channel="wiki",
        query="wiki?",
        db_path=db,
    )
    assert out.get("answer") == "w"
    listed = fqa.list_audit_snapshots(tenant_id="t-wk", db_path=db)
    assert listed["count"] == 1
    item = listed["items"][0]
    assert item["runtime_authority"] == "wiki_kb"
    assert (item.get("meta") or {}).get("channel") == "wiki"

    skipped = fqa.maybe_record_wiki_kb_hotpath(
        tenant_id="",
        response={"answer": "x", "abstained": True},
        channel="kb",
        db_path=db,
    )
    assert skipped.get("answer") == "x"
    assert fqa.list_audit_snapshots(tenant_id="t-wk", db_path=db)["count"] == 1


def test_bare_list_hotpath_writes(tmp_path, monkeypatch):
    """裸 wiki/kb list 热路径落 Query 快照；空 tenant 跳过。"""
    db = str(tmp_path / "fqa-bl.sqlite3")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_HOTPATH", "1")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_DB", db)
    fqa.maybe_record_bare_list_hotpath(
        tenant_id="t-bl",
        hits=[{"title": "p1", "source": "s1", "text": "x"}],
        channel="wiki",
        query="bare?",
        db_path=db,
    )
    listed = fqa.list_audit_snapshots(tenant_id="t-bl", db_path=db)
    assert listed["count"] == 1
    item = listed["items"][0]
    assert item["runtime_authority"] == "bare_list_retrieve"
    assert (item.get("meta") or {}).get("op") == "bare_list_retrieve"
    assert (item.get("meta") or {}).get("channel") == "wiki"

    fqa.maybe_record_bare_list_hotpath(
        tenant_id="",
        hits=[{"title": "x"}],
        channel="kb",
        db_path=db,
    )
    assert fqa.list_audit_snapshots(tenant_id="t-bl", db_path=db)["count"] == 1


def test_kb_qa_hotpath_writes(tmp_path, monkeypatch):
    """KB Q&A/CRAG 热路径落 Query 快照；空 tenant 跳过。"""
    db = str(tmp_path / "fqa-kq.sqlite3")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_HOTPATH", "1")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_DB", db)
    fqa.maybe_record_kb_qa_hotpath(
        tenant_id="t-kq",
        retrieved_text="answer body",
        citations=[{"source": "doc:1", "text": "hit"}],
        query="qa?",
        route="crag",
        db_path=db,
    )
    listed = fqa.list_audit_snapshots(tenant_id="t-kq", db_path=db)
    assert listed["count"] == 1
    item = listed["items"][0]
    assert item["runtime_authority"] == "kb_qa_retrieve"
    assert (item.get("meta") or {}).get("op") == "kb_qa_retrieve"
    assert (item.get("meta") or {}).get("route") == "crag"

    fqa.maybe_record_kb_qa_hotpath(
        tenant_id="",
        retrieved_text="x",
        citations=[],
        db_path=db,
    )
    assert fqa.list_audit_snapshots(tenant_id="t-kq", db_path=db)["count"] == 1


def test_knowledge_retrieve_hotpath_writes(tmp_path, monkeypatch):
    """统一 knowledge_retrieve 热路径落 Query 快照；空 tenant 跳过。"""
    db = str(tmp_path / "fqa-kr.sqlite3")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_HOTPATH", "1")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_DB", db)
    fqa.maybe_record_knowledge_retrieve_hotpath(
        tenant_id="t-kr",
        hits=[{"title": "p1", "source": "wiki", "source_type": "wiki"}],
        query="kr?",
        route="rrf",
        db_path=db,
    )
    listed = fqa.list_audit_snapshots(tenant_id="t-kr", db_path=db)
    assert listed["count"] == 1
    item = listed["items"][0]
    assert item["runtime_authority"] == "knowledge_retrieve"
    assert (item.get("meta") or {}).get("op") == "knowledge_retrieve"
    assert (item.get("meta") or {}).get("route") == "rrf"

    fqa.maybe_record_knowledge_retrieve_hotpath(
        tenant_id="",
        hits=[{"title": "x"}],
        db_path=db,
    )
    assert fqa.list_audit_snapshots(tenant_id="t-kr", db_path=db)["count"] == 1


def test_fact_requires_after_snapshot(tmp_path):
    """Fact 快照缺 after 必须拒绝。"""
    db = str(tmp_path / "fqa.sqlite3")
    with pytest.raises(fqa.FactQueryAuditError) as ei:
        fqa.record_audit_snapshot(
            tenant_id="t",
            kind="fact",
            subject_ref="f1",
            before_snapshot={"a": 1},
            after_snapshot={},
            db_path=db,
        )
    assert "after_snapshot_required" in str(ei.value)


def test_tenant_isolation(tmp_path):
    """跨租户列表不泄漏。"""
    db = str(tmp_path / "fqa.sqlite3")
    fqa.record_audit_snapshot(
        tenant_id="t-a",
        kind="query",
        subject_ref="q1",
        after_snapshot={"abstained": True, "citations": []},
        runtime_authority="query_gateway",
        db_path=db,
    )
    a = fqa.list_audit_snapshots(tenant_id="t-a", db_path=db)
    b = fqa.list_audit_snapshots(tenant_id="t-b", db_path=db)
    assert a["count"] == 1
    assert b["count"] == 0


def test_unified_kinds_share_fields(tmp_path):
    """fact 与 query 同 schema 字段。"""
    db = str(tmp_path / "fqa.sqlite3")
    fqa.record_audit_snapshot(
        tenant_id="t",
        kind="fact",
        subject_ref="f1",
        before_snapshot={"status": "draft"},
        after_snapshot={"status": "active"},
        runtime_authority="fact_ledger",
        db_path=db,
    )
    fqa.record_audit_snapshot(
        tenant_id="t",
        kind="query",
        subject_ref="q1",
        after_snapshot={"results": 0, "abstained": True},
        runtime_authority="query_gateway",
        db_path=db,
    )
    listed = fqa.list_audit_snapshots(tenant_id="t", db_path=db)
    assert listed["count"] == 2
    for item in listed["items"]:
        assert "before_snapshot" in item
        assert "after_snapshot" in item
        assert "runtime_authority" in item
        assert item["certified"] is False


def test_wiki_context_n21_fail_falls_back_to_audit(tmp_path, monkeypatch):
    """sys_wiki_context：n21 信封失败时仍兜底落 N19 Query 快照。"""
    db = str(tmp_path / "fqa-wc.sqlite3")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_HOTPATH", "1")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_DB", db)

    def _boom(*_a, **_k):
        raise RuntimeError("n21 attach forced fail")

    monkeypatch.setattr(
        "core.harness.knowledge_pipeline.query_abstain_citations.attach_list_retrieve_n21_envelope",
        _boom,
    )
    monkeypatch.setattr(
        "core.harness.syscalls.retrieval.sys_wiki_retrieve",
        lambda *_a, **_k: [{"title": "t1", "text": "body", "source": "wiki"}],
    )

    from core.harness.syscalls.wiki_context import sys_wiki_context

    out = sys_wiki_context("q?", tenant_id="t-wc", attach_n21_query=True)
    assert isinstance(out, dict)
    listed = fqa.list_audit_snapshots(tenant_id="t-wc", db_path=db)
    assert listed["count"] == 1
    assert (listed["items"][0].get("meta") or {}).get("channel") == "wiki_context"


def test_wiki_structured_query_api_hotpath(tmp_path, monkeypatch):
    """wiki_structured_query_api：有 tenant 时落 N19；certified 恒 false。"""
    db = str(tmp_path / "fqa-ws.sqlite3")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_HOTPATH", "1")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_DB", db)
    monkeypatch.setattr(
        "core.harness.knowledge.wiki_structured_query.structured_query",
        lambda _q: {
            "result": "ok",
            "template_used": "概念查询",
            "confidence": 0.9,
        },
    )

    from core.api.core_facade import wiki_structured_query_api

    out = wiki_structured_query_api("什么是RAG", tenant_id="t-ws")
    assert out.get("certified") is False
    assert out.get("n19_full_conformance") is False
    listed = fqa.list_audit_snapshots(tenant_id="t-ws", db_path=db)
    assert listed["count"] == 1
    assert (listed["items"][0].get("meta") or {}).get("channel") == "wiki_structured"

    skip = wiki_structured_query_api("什么是RAG", tenant_id="")
    assert skip.get("certified") is False
    assert fqa.list_audit_snapshots(tenant_id="t-ws", db_path=db)["count"] == 1


def test_ontology_context_hotpath(tmp_path, monkeypatch):
    """sys_ontology_context：有 tenant 时落 N19；空 tenant 跳过。"""
    db = str(tmp_path / "fqa-oc.sqlite3")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_HOTPATH", "1")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_DB", db)

    class _Onto:
        triples = []

    monkeypatch.setattr(
        "core.harness.knowledge.knowledge_ontology.get_ontology",
        lambda: _Onto(),
    )
    monkeypatch.setattr(
        "core.harness.knowledge.wiki_engine.search_pages",
        lambda *_a, **_k: [{"title": "p1", "summary": "s"}],
    )

    from core.harness.syscalls.ontology_context import sys_ontology_context

    out = sys_ontology_context(
        "q?",
        tenant_id="t-oc",
        include_contradictions=False,
        include_gaps=False,
        include_state_summary=False,
    )
    assert out.get("certified") is False
    assert out.get("n19_full_conformance") is False
    listed = fqa.list_audit_snapshots(tenant_id="t-oc", db_path=db)
    assert listed["count"] == 1
    assert (listed["items"][0].get("meta") or {}).get("channel") == "ontology_context"

    sys_ontology_context("q?", tenant_id="", include_gaps=False)
    assert fqa.list_audit_snapshots(tenant_id="t-oc", db_path=db)["count"] == 1


@pytest.mark.asyncio
async def test_ontology_urn_hotpath(tmp_path, monkeypatch):
    """URN sys_ontology_context：有 tenant 时落 N19；空 tenant 跳过。"""
    db = str(tmp_path / "fqa-urn.sqlite3")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_HOTPATH", "1")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_DB", db)

    class _Store:
        def get_downstream(self, urn, depth):
            return [{"s": urn, "p": "uses", "o": "x"}]

        def get_upstream(self, urn, depth):
            return []

    monkeypatch.setattr(
        "core.harness.ontology_engine.triple_store.get_triple_store",
        lambda: _Store(),
    )

    from core.harness.syscalls.ontology import sys_ontology_context

    out = await sys_ontology_context(
        "urn:aiplat:agent:demo", depth=1, tenant_id="t-urn"
    )
    assert out.get("certified") is False
    assert out.get("n19_full_conformance") is False
    listed = fqa.list_audit_snapshots(tenant_id="t-urn", db_path=db)
    assert listed["count"] == 1
    assert (listed["items"][0].get("meta") or {}).get("channel") == "ontology_urn"

    await sys_ontology_context("urn:aiplat:agent:demo", tenant_id="")
    assert fqa.list_audit_snapshots(tenant_id="t-urn", db_path=db)["count"] == 1


@pytest.mark.asyncio
async def test_ontology_urn_http_hotpath(tmp_path, monkeypatch):
    """HTTP ontology_query / impact：有 tenant 落盘；certified 恒 false。"""
    db = str(tmp_path / "fqa-urn-http.sqlite3")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_HOTPATH", "1")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_DB", db)

    class _Store:
        def get_downstream(self, urn, depth):
            return [{"s": urn, "p": "uses", "o": "y"}]

        def get_upstream(self, urn, depth):
            return [{"s": "z", "p": "calls", "o": urn}]

    monkeypatch.setattr(
        "core.api.routers.ontology_routes.get_triple_store",
        lambda: _Store(),
    )

    from core.api.routers.ontology_routes import ontology_query, ontology_impact

    q = await ontology_query(
        {"urn": "urn:aiplat:skill:demo", "tenant_id": "t-http", "depth": 1}
    )
    assert q.get("certified") is False
    listed = fqa.list_audit_snapshots(tenant_id="t-http", db_path=db)
    assert listed["count"] == 1
    assert (listed["items"][0].get("meta") or {}).get("channel") == "ontology_urn_http"

    await ontology_impact("skill:demo", depth=1, tenant_id="t-http")
    assert fqa.list_audit_snapshots(tenant_id="t-http", db_path=db)["count"] == 2

    skip = await ontology_query({"urn": "urn:aiplat:skill:demo", "tenant_id": ""})
    assert skip.get("certified") is False
    assert fqa.list_audit_snapshots(tenant_id="t-http", db_path=db)["count"] == 2


def test_wiki_search_pages_api_hotpath(tmp_path, monkeypatch):
    """wiki_search_pages_api：有 tenant 时落 N19；certified 恒 false。"""
    db = str(tmp_path / "fqa-wp.sqlite3")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_HOTPATH", "1")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_DB", db)
    monkeypatch.setattr(
        "core.harness.knowledge.wiki_engine.search_pages",
        lambda *_a, **_k: [{"title": "p1", "summary": "s"}],
    )

    from core.api.core_facade import wiki_search_pages_api

    out = wiki_search_pages_api("RAG", tenant_id="t-wp")
    assert out.get("certified") is False
    assert out.get("n19_full_conformance") is False
    listed = fqa.list_audit_snapshots(tenant_id="t-wp", db_path=db)
    assert listed["count"] == 1
    assert (listed["items"][0].get("meta") or {}).get("channel") == "wiki_pages"

    skip = wiki_search_pages_api("RAG", tenant_id="")
    assert skip.get("certified") is False
    assert fqa.list_audit_snapshots(tenant_id="t-wp", db_path=db)["count"] == 1


@pytest.mark.asyncio
async def test_graph_neighbors_hotpath(tmp_path, monkeypatch):
    """sys_graph_neighbors：显式 tenant 落 N19；空 tenant 跳过。"""
    db = str(tmp_path / "fqa-gn.sqlite3")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_HOTPATH", "1")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_DB", db)

    class _Node:
        entity_name = "e1"
        out_edges = []
        in_edges = []

    class _Graph:
        def get_node(self, _n):
            return _Node()

        def find_by_name(self, _n):
            return None

    monkeypatch.setattr(
        "core.harness.ontology_engine.graph_index.GraphIndex.load",
        lambda *_a, **_k: _Graph(),
    )

    from core.harness.syscalls.graph import sys_graph_neighbors

    out = await sys_graph_neighbors("e1", tenant_id="t-gn")
    assert out.get("certified") is False
    assert out.get("n19_full_conformance") is False
    listed = fqa.list_audit_snapshots(tenant_id="t-gn", db_path=db)
    assert listed["count"] == 1
    assert (listed["items"][0].get("meta") or {}).get("channel") == "graph_neighbors"

    await sys_graph_neighbors("e1", tenant_id="")
    assert fqa.list_audit_snapshots(tenant_id="t-gn", db_path=db)["count"] == 1


@pytest.mark.asyncio
async def test_graph_query_hotpath(tmp_path, monkeypatch):
    """sys_graph_query：显式 tenant 落 N19；空 tenant 跳过；stats 契约。"""
    db = str(tmp_path / "fqa-gq.sqlite3")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_HOTPATH", "1")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_DB", db)

    class _Graph:
        def stats(self):
            return {"domain_id": "d", "node_count": 3, "edge_count": 2, "avg_degree": 0.7}

        def get_entity_classes(self):
            return ["A", "B"]

    monkeypatch.setattr(
        "core.harness.ontology_engine.graph_index.GraphIndex.load",
        lambda *_a, **_k: _Graph(),
    )

    from core.harness.syscalls.graph import sys_graph_query

    out = await sys_graph_query("", operation="stats", tenant_id="t-gq")
    assert out.get("success") is True
    assert out.get("data", {}).get("nodes") == 3
    assert out.get("certified") is False
    assert out.get("n19_full_conformance") is False
    listed = fqa.list_audit_snapshots(tenant_id="t-gq", db_path=db)
    assert listed["count"] == 1
    assert (listed["items"][0].get("meta") or {}).get("channel") == "graph_query"

    classes = await sys_graph_query("", operation="classes", tenant_id="t-gq")
    assert classes.get("success") is True
    assert "A" in (classes.get("data") or {}).get("classes", [])
    assert fqa.list_audit_snapshots(tenant_id="t-gq", db_path=db)["count"] == 2

    await sys_graph_query("", operation="stats", tenant_id="")
    assert fqa.list_audit_snapshots(tenant_id="t-gq", db_path=db)["count"] == 2
