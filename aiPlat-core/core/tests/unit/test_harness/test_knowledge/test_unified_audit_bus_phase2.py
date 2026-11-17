"""J5：N24 Unified Audit 写总线（幂等 / revision 热路径 / materialize / 诚实锁）。"""
from __future__ import annotations

import pytest
import pytest_asyncio

from core.harness.infrastructure.action_execution import persist_execution
from core.harness.knowledge_pipeline.fact_ledger import FactLedger
from core.harness.knowledge_pipeline.ontology_package import publish_package
from core.harness.knowledge_pipeline.unified_audit_bus import (
    append_unified_audit_event,
    evaluate_unified_audit_bus_gate,
    list_unified_audit_bus_events,
    materialize_unified_audit_from_view,
    run_unified_audit_bus_suite,
)
from core.harness.knowledge_pipeline.unified_audit_view import list_unified_audit_events


@pytest_asyncio.fixture
async def harness(tmp_path, monkeypatch):
    bus_db = str(tmp_path / "bus.sqlite3")
    monkeypatch.setenv("AIPLAT_UNIFIED_AUDIT_BUS_DB", bus_db)
    pkg_db = str(tmp_path / "pkg.sqlite3")
    act_db = str(tmp_path / "act.sqlite3")
    ledger = FactLedger(
        db_path=str(tmp_path / "fact_ledger.sqlite3"),
        raw_dir=tmp_path / "raw",
        action_execution_db_path=act_db,
    )
    await ledger.initialize()
    return ledger, pkg_db, act_db, bus_db


def test_append_idempotent(tmp_path):
    """同 tenant+event_id 再写不覆盖。"""
    db = str(tmp_path / "bus.sqlite3")
    a = append_unified_audit_event(
        tenant_id="t1",
        event_id="e1",
        stream="manual",
        event_type="a",
        occurred_at=1.0,
        db_path=db,
    )
    b = append_unified_audit_event(
        tenant_id="t1",
        event_id="e1",
        stream="manual",
        event_type="b",
        occurred_at=9.0,
        db_path=db,
    )
    assert a["idempotent_hit"] is False
    assert b["idempotent_hit"] is True
    assert b["event_type"] == "a"


@pytest.mark.asyncio
async def test_revision_emit_to_bus(harness):
    """revision_audit 热路径写入 bus。"""
    ledger, _pkg, _act, bus_db = harness
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="c1",
        kind="file",
        uri="file://n24/bus.txt",
        content=b"v1",
        connector="n24",
    )
    evidence = [
        {
            "source_id": src["source_id"],
            "locator": "x",
            "quote": "v1",
            "fetched_at": src["fetched_at"],
        }
    ]
    fact = await ledger.put_fact(
        tenant_id="t1",
        collection_id="c1",
        subject="door",
        predicate="state",
        object="locked",
        evidence=evidence,
        source_policy="n24",
        extractor_version="t",
        review_status="draft",
        confidence=0.5,
        revision=1,
        enforce_write_gates=False,
    )
    await ledger.put_fact(
        tenant_id="t1",
        collection_id="c1",
        subject="door",
        predicate="state",
        object="unlocked",
        evidence=evidence,
        source_policy="n24",
        extractor_version="t",
        review_status="draft",
        confidence=0.5,
        fact_id=fact["fact_id"],
        revision=2,
        enforce_write_gates=False,
        revision_actor="tester",
        revision_reason="bump",
    )
    rows = list_unified_audit_bus_events(
        tenant_id="t1", stream="revision_audit", db_path=bus_db
    )
    assert len(rows) >= 1
    assert rows[0]["stream"] == "revision_audit"


@pytest.mark.asyncio
async def test_materialize_and_view_bus_stream(harness):
    """materialize 三流进 bus；view streams=bus 可见。"""
    ledger, pkg_db, act_db, bus_db = harness
    publish_package(
        tenant_id="t1",
        package_id="p1",
        version="1.0.0",
        schema=["X"],
        db_path=pkg_db,
    )
    persist_execution(
        {
            "tenant_id": "t1",
            "idempotency_key": "k1",
            "action_id": "knowledge_revision:x",
            "actor": "a",
            "status": "succeeded",
            "started_at": 1.0,
            "completed_at": 2.0,
        },
        db_path=act_db,
    )
    mat = await materialize_unified_audit_from_view(
        tenant_id="t1",
        package_db_path=pkg_db,
        action_execution_db_path=act_db,
        bus_db_path=bus_db,
        fact_ledger=ledger,
        limit=50,
    )
    assert mat["certified"] is False
    assert int(mat["written"]) >= 1
    view = await list_unified_audit_events(
        tenant_id="t1",
        streams=["bus"],
        bus_db_path=bus_db,
        fact_ledger=ledger,
        limit=50,
    )
    assert view["certified"] is False
    assert any(e.get("stream") == "bus" for e in view["events"])


@pytest.mark.asyncio
async def test_cross_tenant_empty(harness):
    """跨租户 bus 列表为空。"""
    _ledger, _pkg, _act, bus_db = harness
    append_unified_audit_event(
        tenant_id="t1",
        event_id="only-t1",
        stream="manual",
        event_type="x",
        db_path=bus_db,
    )
    other = list_unified_audit_bus_events(tenant_id="t2", db_path=bus_db)
    assert other == []


@pytest.mark.asyncio
async def test_suite_and_gate_honesty():
    """suite/gate certified 恒 false。"""
    suite = await run_unified_audit_bus_suite()
    assert suite["ok"] is True
    assert suite["certified"] is False
    assert suite["n24_full_conformance"] is False
    gate = evaluate_unified_audit_bus_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    bad = evaluate_unified_audit_bus_gate(
        {**suite, "certified": True, "n24_full_conformance": True}
    )
    assert bad["ok"] is False
    assert "honesty_certified_flag_forbidden" in bad["issues"]
