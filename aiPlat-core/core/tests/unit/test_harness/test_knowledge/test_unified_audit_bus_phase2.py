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
async def test_package_and_action_hotpath_to_bus(harness):
    """J6：publish_package / persist_execution 热路径直接入 bus。"""
    _ledger, pkg_db, act_db, bus_db = harness
    pub = publish_package(
        tenant_id="t1",
        package_id="p1",
        version="1.0.0",
        schema=["X"],
        db_path=pkg_db,
    )
    assert pub["status"] == "published"
    pkg_rows = list_unified_audit_bus_events(
        tenant_id="t1", stream="package", db_path=bus_db
    )
    assert any(e.get("event_id") == "pkg:p1:1.0.0" for e in pkg_rows)

    act = persist_execution(
        {
            "tenant_id": "t1",
            "idempotency_key": "k-hot",
            "action_id": "knowledge_revision:hot",
            "actor": "a",
            "status": "succeeded",
            "started_at": 1.0,
            "completed_at": 2.0,
        },
        db_path=act_db,
    )
    act_rows = list_unified_audit_bus_events(
        tenant_id="t1", stream="action_execution", db_path=bus_db
    )
    assert any(e.get("event_id") == act["execution_id"] for e in act_rows)


@pytest.mark.asyncio
async def test_action_store_hotpath_to_bus(harness, tmp_path):
    """J7：ActionStore.insert_audit 热路径直接入 bus。"""
    _ledger, _pkg, _act, bus_db = harness
    from core.harness.infrastructure.action_store import ActionStore

    store = ActionStore(str(tmp_path / "action_store.sqlite3"))
    await store.initialize()
    aid = await store.insert_audit(
        {
            "action_id": "knowledge_revision:store",
            "entity_id": "e1",
            "domain_id": "d1",
            "actor": "a",
            "result_status": "executed",
            "tenant_id": "t1",
            "params": {"tenant_id": "t1"},
        }
    )
    rows = list_unified_audit_bus_events(
        tenant_id="t1", stream="action_store", db_path=bus_db
    )
    assert any(e.get("event_id") == str(aid) for e in rows)
    other = list_unified_audit_bus_events(
        tenant_id="t2", stream="action_store", db_path=bus_db
    )
    assert other == []


@pytest.mark.asyncio
async def test_fact_query_hotpath_to_bus(harness, tmp_path, monkeypatch):
    """J11：Fact/Query record_audit_snapshot 热路径直接入 bus。"""
    _ledger, _pkg, _act, bus_db = harness
    from core.harness.knowledge_pipeline.fact_query_audit import record_audit_snapshot

    fqa_db = str(tmp_path / "fqa.sqlite3")
    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_BUS_HOTPATH", "1")
    row = record_audit_snapshot(
        tenant_id="t1",
        kind="query",
        subject_ref="fqa-hot",
        after_snapshot={"abstained": True, "citations": []},
        runtime_authority="query_gateway",
        db_path=fqa_db,
    )
    rows = list_unified_audit_bus_events(
        tenant_id="t1", stream="fact_query_audit", db_path=bus_db
    )
    assert any(e.get("event_id") == f"fqa:{row['snapshot_id']}" for e in rows)

    monkeypatch.setenv("AIPLAT_FACT_QUERY_AUDIT_BUS_HOTPATH", "0")
    row2 = record_audit_snapshot(
        tenant_id="t1",
        kind="query",
        subject_ref="fqa-off",
        after_snapshot={"abstained": True, "citations": []},
        runtime_authority="query_gateway",
        db_path=fqa_db,
    )
    rows2 = list_unified_audit_bus_events(
        tenant_id="t1", stream="fact_query_audit", db_path=bus_db
    )
    assert not any(e.get("event_id") == f"fqa:{row2['snapshot_id']}" for e in rows2)


@pytest.mark.asyncio
async def test_action_store_physical_tenant_column(tmp_path):
    """J8：物理 tenant_id 列写入 + list_audit 召回前过滤；跨租户空。"""
    from core.harness.infrastructure.action_store import ActionStore

    store_db = str(tmp_path / "action_store_tenant.sqlite3")
    store = ActionStore(store_db)
    await store.initialize()
    await store.insert_audit(
        {
            "action_id": "knowledge_revision:tcol",
            "entity_id": "e1",
            "domain_id": "d1",
            "actor": "a",
            "result_status": "executed",
            "tenant_id": "t1",
            "params": {},
        }
    )
    await store.insert_audit(
        {
            "action_id": "knowledge_revision:tcol2",
            "entity_id": "e2",
            "domain_id": "d1",
            "actor": "a",
            "result_status": "executed",
            "tenant_id": "t2",
            "params": {"tenant_id": "t2"},
        }
    )
    t1 = await store.list_audit(tenant_id="t1", limit=50)
    assert len(t1) == 1
    assert t1[0].get("tenant_id") == "t1"
    t2 = await store.list_audit(tenant_id="t2", limit=50)
    assert len(t2) == 1
    view = await list_unified_audit_events(
        tenant_id="t1",
        streams=["action_store"],
        action_store_db_path=store_db,
        limit=50,
    )
    assert view["certified"] is False
    assert len(view["events"]) == 1
    assert view["events"][0]["event_id"]
    other = await list_unified_audit_events(
        tenant_id="other",
        streams=["action_store"],
        action_store_db_path=store_db,
        limit=50,
    )
    assert other["count"] == 0


@pytest.mark.asyncio
async def test_action_store_tenant_backfill(tmp_path):
    """J9：存量空物理列从 params 回填；幂等；无 params 租户保持空；跨租户空。"""
    import aiosqlite
    import json

    from core.harness.infrastructure.action_store import ActionStore

    store_db = str(tmp_path / "action_store_backfill.sqlite3")
    store = ActionStore(store_db)
    await store.initialize()
    # 模拟 J8 前遗留行：物理列空，仅 params 有 tenant
    async with aiosqlite.connect(store_db) as db:
        await db.execute(
            """
            INSERT INTO action_audit (
                audit_id, action_id, entity_id, domain_id, tenant_id,
                params, result_status, actor
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "aud_legacy_t1",
                "knowledge_revision:legacy",
                "e_legacy",
                "d1",
                "",
                json.dumps({"tenant_id": "t_legacy"}, ensure_ascii=False),
                "executed",
                "sys",
            ),
        )
        await db.execute(
            """
            INSERT INTO action_audit (
                audit_id, action_id, entity_id, domain_id, tenant_id,
                params, result_status, actor
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "aud_legacy_empty",
                "knowledge_revision:orphan",
                "e_orphan",
                "d1",
                "",
                json.dumps({"note": "no-tenant"}, ensure_ascii=False),
                "executed",
                "sys",
            ),
        )
        await db.commit()

    first = await store.backfill_tenant_id()
    assert first["updated"] == 1
    rows = await store.list_audit(tenant_id="t_legacy", limit=50)
    assert len(rows) == 1
    assert rows[0].get("tenant_id") == "t_legacy"
    assert rows[0].get("audit_id") == "aud_legacy_t1"
    # 无 params.tenant_id 的行不猜测默认租户
    empty = await store.list_audit(entity_id="e_orphan", limit=50)
    assert len(empty) == 1
    assert (empty[0].get("tenant_id") or "") == ""
    second = await store.backfill_tenant_id()
    assert second["updated"] == 0
    assert second["remaining_empty"] >= 1
    view = await list_unified_audit_events(
        tenant_id="t_legacy",
        streams=["action_store"],
        action_store_db_path=store_db,
        limit=50,
    )
    assert view["certified"] is False
    assert len(view["events"]) == 1
    other = await list_unified_audit_events(
        tenant_id="other",
        streams=["action_store"],
        action_store_db_path=store_db,
        limit=50,
    )
    assert other["count"] == 0


@pytest.mark.asyncio
async def test_materialize_and_view_bus_stream(harness):
    """materialize 三流进 bus；view streams=bus 可见（热路径后幂等 skip 亦可）。"""
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
    assert int(mat["written"]) + int(mat["skipped"]) >= 1
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
