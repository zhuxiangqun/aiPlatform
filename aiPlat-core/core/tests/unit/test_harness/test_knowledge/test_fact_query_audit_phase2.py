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
