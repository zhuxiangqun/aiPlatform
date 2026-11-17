"""I4：N24 Revision→ActionExecution 桥接（certified 恒 false；非全量总线）。"""
from __future__ import annotations

import pytest

from core.harness.infrastructure.action_execution import lookup_execution
from core.harness.knowledge_pipeline.fact_ledger import (
    FactLedger,
    evaluate_revision_action_bridge_gate,
    run_revision_action_bridge_suite,
)


@pytest.fixture
async def ledger(tmp_path):
    store = FactLedger(
        db_path=str(tmp_path / "fact_ledger.sqlite3"),
        raw_dir=tmp_path / "raw",
        action_execution_db_path=str(tmp_path / "action_execution.sqlite3"),
    )
    await store.initialize()
    return store


async def _seed_and_approve(ledger: FactLedger):
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="c1",
        kind="file",
        uri="file://n24/bridge.txt",
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
        revision_actor="t",
        revision_reason="bump",
    )
    req = await ledger.request_revision_restore(
        tenant_id="t1",
        entity_type="fact",
        entity_id=fact["fact_id"],
        target_revision=1,
        requester="alice",
        reason="need",
    )
    approved = await ledger.approve_revision_restore(
        req["request_id"], tenant_id="t1", approver="bob", reason="ok"
    )
    return fact["fact_id"], approved


@pytest.mark.asyncio
async def test_approve_creates_bridge_and_execution(ledger: FactLedger):
    fid, approved = await _seed_and_approve(ledger)
    bridge = approved["action_bridge"]
    assert bridge["execution_id"]
    assert bridge["event_type"] == "restore_approve"
    rows = await ledger.list_revision_action_bridges(
        tenant_id="t1", entity_type="fact", entity_id=fid
    )
    assert len(rows) == 1
    exec_row = lookup_execution(
        "t1",
        f"rev-bridge:{bridge['audit_id']}",
        db_path=ledger.action_execution_db_path,
    )
    assert exec_row is not None
    assert exec_row["execution_id"] == bridge["execution_id"]
    assert exec_row["action_id"] == "knowledge_revision:restore_approve"


@pytest.mark.asyncio
async def test_bridge_idempotent(ledger: FactLedger):
    _fid, approved = await _seed_and_approve(ledger)
    bridge = approved["action_bridge"]
    again = await ledger.bridge_revision_audit_to_action(
        audit_event={
            "tenant_id": "t1",
            "audit_id": bridge["audit_id"],
            "entity_type": "fact",
            "entity_id": bridge["entity_id"],
            "event_type": "restore_approve",
            "revision": 1,
            "actor": "bob",
            "reason": "ok",
        },
        action_id="knowledge_revision:restore_approve",
    )
    assert again["idempotent"] is True
    assert again["execution_id"] == bridge["execution_id"]


@pytest.mark.asyncio
async def test_cross_tenant_empty(ledger: FactLedger):
    await _seed_and_approve(ledger)
    assert await ledger.list_revision_action_bridges(tenant_id="t2") == []


@pytest.mark.asyncio
async def test_suite_and_gate_honesty():
    suite = await run_revision_action_bridge_suite()
    assert suite["ok"] is True
    assert suite["certified"] is False
    assert suite["n24_full_conformance"] is False
    gate = evaluate_revision_action_bridge_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    honesty = evaluate_revision_action_bridge_gate(
        {**suite, "certified": True, "n24_full_conformance": True}
    )
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
