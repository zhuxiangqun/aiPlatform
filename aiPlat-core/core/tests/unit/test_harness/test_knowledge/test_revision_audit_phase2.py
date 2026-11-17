"""I2：N24 Revision Audit 账本内事件（certified 恒 false；非统一总线）。"""
from __future__ import annotations

import pytest

from core.harness.knowledge_pipeline.fact_ledger import (
    FactLedger,
    evaluate_revision_audit_gate,
    run_revision_audit_suite,
)


@pytest.fixture
async def ledger(tmp_path):
    store = FactLedger(
        db_path=str(tmp_path / "fact_ledger.sqlite3"),
        raw_dir=tmp_path / "raw",
    )
    await store.initialize()
    return store


async def _seed_fact_bump(ledger: FactLedger):
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="c1",
        kind="file",
        uri="file://n24/audit.txt",
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
    return fact["fact_id"]


@pytest.mark.asyncio
async def test_archive_emits_audit(ledger: FactLedger):
    fid = await _seed_fact_bump(ledger)
    rows = await ledger.list_revision_audit(
        tenant_id="t1", entity_type="fact", entity_id=fid, event_type="archive"
    )
    assert len(rows) == 1
    assert rows[0]["revision"] == 1
    assert rows[0]["actor"] == "tester"


@pytest.mark.asyncio
async def test_restore_emits_audit(ledger: FactLedger):
    fid = await _seed_fact_bump(ledger)
    await ledger.restore_fact_at_revision(
        fid,
        tenant_id="t1",
        target_revision=1,
        actor="tester",
        reason="restore",
        enforce_write_gates=False,
    )
    restores = await ledger.list_revision_audit(
        tenant_id="t1", entity_type="fact", entity_id=fid, event_type="restore"
    )
    assert len(restores) == 1
    assert restores[0]["revision"] == 1
    assert restores[0]["to_revision"] == 3
    archives = await ledger.list_revision_audit(
        tenant_id="t1", entity_type="fact", entity_id=fid, event_type="archive"
    )
    # bump archives r1; restore archives r2 before writing r3
    assert len(archives) == 2


@pytest.mark.asyncio
async def test_cross_tenant_empty(ledger: FactLedger):
    fid = await _seed_fact_bump(ledger)
    assert await ledger.list_revision_audit(tenant_id="t2", entity_id=fid) == []


@pytest.mark.asyncio
async def test_suite_and_gate_honesty():
    suite = await run_revision_audit_suite()
    assert suite["ok"] is True
    assert suite["certified"] is False
    assert suite["n24_full_conformance"] is False
    gate = evaluate_revision_audit_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    honesty = evaluate_revision_audit_gate(
        {**suite, "certified": True, "n24_full_conformance": True}
    )
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
