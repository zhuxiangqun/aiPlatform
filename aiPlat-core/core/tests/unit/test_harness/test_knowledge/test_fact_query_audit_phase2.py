"""N19 Fact/Query 统一审计 deepen 单元测试。"""
from __future__ import annotations

import pytest

from core.harness.knowledge_pipeline import fact_query_audit as fqa


def test_suite_passes_and_gate_never_certifies():
    """套件全绿且 certified / n19_full 恒 false。"""
    suite = fqa.run_fact_query_audit_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["certified"] is False
    assert suite["n19_full_conformance"] is False

    gate = fqa.evaluate_fact_query_audit_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["n19_full_conformance"] is False
    assert gate["issues"] == []


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
