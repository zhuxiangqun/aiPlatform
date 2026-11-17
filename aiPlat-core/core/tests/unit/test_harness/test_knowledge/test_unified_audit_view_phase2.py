"""J3：N24 Package+Action+revision_audit 只读统一视图（certified 恒 false；非全量总线）。"""
from __future__ import annotations

import pytest
import pytest_asyncio

from core.harness.infrastructure.action_execution import persist_execution
from core.harness.knowledge_pipeline.fact_ledger import FactLedger
from core.harness.knowledge_pipeline.ontology_package import publish_package
from core.harness.knowledge_pipeline.unified_audit_view import (
    evaluate_unified_audit_view_gate,
    list_unified_audit_events,
    run_unified_audit_view_suite,
)


@pytest_asyncio.fixture
async def harness(tmp_path):
    pkg_db = str(tmp_path / "pkg.sqlite3")
    act_db = str(tmp_path / "act.sqlite3")
    store_db = str(tmp_path / "action_store.sqlite3")
    bus_db = str(tmp_path / "unified_audit_bus.sqlite3")
    ledger = FactLedger(
        db_path=str(tmp_path / "fact_ledger.sqlite3"),
        raw_dir=tmp_path / "raw",
        action_execution_db_path=act_db,
    )
    await ledger.initialize()
    return ledger, pkg_db, act_db, store_db, bus_db


async def _seed(ledger: FactLedger, pkg_db: str, act_db: str, tenant: str = "t1"):
    publish_package(
        tenant_id=tenant,
        package_id="demo-pkg",
        version="1.0.0",
        schema=["InstallOrder"],
        db_path=pkg_db,
    )
    persist_execution(
        {
            "tenant_id": tenant,
            "idempotency_key": "ua-1",
            "action_id": "knowledge_revision:probe",
            "actor": "a",
            "status": "succeeded",
            "started_at": 1.0,
            "completed_at": 2.0,
        },
        db_path=act_db,
    )
    src = await ledger.register_source(
        tenant_id=tenant,
        collection_id="c1",
        kind="file",
        uri="file://n24/ua.txt",
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
        tenant_id=tenant,
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
        tenant_id=tenant,
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
        revision_actor="t",
        revision_reason="bump",
    )


@pytest.mark.asyncio
async def test_three_streams_present(harness):
    ledger, pkg_db, act_db, store_db, bus_db = harness
    await _seed(ledger, pkg_db, act_db)
    view = await list_unified_audit_events(
        tenant_id="t1",
        package_db_path=pkg_db,
        action_execution_db_path=act_db,
        action_store_db_path=store_db,
        bus_db_path=bus_db,
        fact_ledger=ledger,
    )
    tags = {e["stream"] for e in view["events"]}
    assert tags >= {"package", "action_execution", "revision_audit"}
    assert view["certified"] is False
    assert view["n24_full_conformance"] is False


@pytest.mark.asyncio
async def test_stream_filter_config(harness):
    ledger, pkg_db, act_db, store_db, bus_db = harness
    await _seed(ledger, pkg_db, act_db)
    view = await list_unified_audit_events(
        tenant_id="t1",
        streams=["revision_audit"],
        package_db_path=pkg_db,
        action_execution_db_path=act_db,
        action_store_db_path=store_db,
        bus_db_path=bus_db,
        fact_ledger=ledger,
    )
    tags = {e["stream"] for e in view["events"]}
    assert tags == {"revision_audit"}


@pytest.mark.asyncio
async def test_cross_tenant_empty(harness):
    ledger, pkg_db, act_db, store_db, bus_db = harness
    await _seed(ledger, pkg_db, act_db)
    view = await list_unified_audit_events(
        tenant_id="t2",
        package_db_path=pkg_db,
        action_execution_db_path=act_db,
        action_store_db_path=store_db,
        bus_db_path=bus_db,
        fact_ledger=ledger,
    )
    assert view["count"] == 0


@pytest.mark.asyncio
async def test_suite_and_gate_honesty():
    suite = await run_unified_audit_view_suite()
    assert suite["ok"] is True
    assert suite["certified"] is False
    assert suite["n24_full_conformance"] is False
    gate = evaluate_unified_audit_view_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    honesty = evaluate_unified_audit_view_gate(
        {**suite, "certified": True, "n24_full_conformance": True}
    )
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
