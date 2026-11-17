"""I3：N24 审批式 Restore（certified 恒 false；非 UI）。"""
from __future__ import annotations

import pytest

from core.harness.knowledge_pipeline.fact_ledger import (
    FactLedger,
    FactLedgerError,
    evaluate_restore_approval_gate,
    run_restore_approval_suite,
)


@pytest.fixture
async def ledger(tmp_path):
    store = FactLedger(
        db_path=str(tmp_path / "fact_ledger.sqlite3"),
        raw_dir=tmp_path / "raw",
    )
    await store.initialize()
    return store


async def _seed_fact(ledger: FactLedger):
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="c1",
        kind="file",
        uri="file://n24/appr.txt",
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
    return fact["fact_id"], evidence


@pytest.mark.asyncio
async def test_request_and_self_approve_rejected(ledger: FactLedger):
    fid, _ = await _seed_fact(ledger)
    req = await ledger.request_revision_restore(
        tenant_id="t1",
        entity_type="fact",
        entity_id=fid,
        target_revision=1,
        requester="alice",
        reason="need",
    )
    assert req["status"] == "pending"
    with pytest.raises(FactLedgerError, match="differ from requester"):
        await ledger.approve_revision_restore(
            req["request_id"], tenant_id="t1", approver="alice", reason="self"
        )


@pytest.mark.asyncio
async def test_approve_applies_restore(ledger: FactLedger):
    fid, _ = await _seed_fact(ledger)
    req = await ledger.request_revision_restore(
        tenant_id="t1",
        entity_type="fact",
        entity_id=fid,
        target_revision=1,
        requester="alice",
        reason="need",
    )
    out = await ledger.approve_revision_restore(
        req["request_id"], tenant_id="t1", approver="bob", reason="ok"
    )
    assert out["status"] == "approved"
    head = await ledger.get_fact(fid, tenant_id="t1")
    assert head is not None
    assert head["object"] == "locked"
    assert head["revision"] == 3


@pytest.mark.asyncio
async def test_reject_leaves_head(ledger: FactLedger):
    fid, evidence = await _seed_fact(ledger)
    req = await ledger.request_revision_restore(
        tenant_id="t1",
        entity_type="fact",
        entity_id=fid,
        target_revision=1,
        requester="alice",
        reason="need",
    )
    out = await ledger.reject_revision_restore(
        req["request_id"], tenant_id="t1", rejector="bob", reason="no"
    )
    assert out["status"] == "rejected"
    head = await ledger.get_fact(fid, tenant_id="t1")
    assert head is not None
    assert head["object"] == "unlocked"
    assert head["revision"] == 2


@pytest.mark.asyncio
async def test_duplicate_pending_rejected(ledger: FactLedger):
    fid, _ = await _seed_fact(ledger)
    await ledger.request_revision_restore(
        tenant_id="t1",
        entity_type="fact",
        entity_id=fid,
        target_revision=1,
        requester="alice",
        reason="one",
    )
    with pytest.raises(FactLedgerError, match="pending restore request"):
        await ledger.request_revision_restore(
            tenant_id="t1",
            entity_type="fact",
            entity_id=fid,
            target_revision=1,
            requester="carol",
            reason="two",
        )


@pytest.mark.asyncio
async def test_suite_and_gate_honesty():
    suite = await run_restore_approval_suite()
    assert suite["ok"] is True
    assert suite["certified"] is False
    assert suite["n24_full_conformance"] is False
    gate = evaluate_restore_approval_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    honesty = evaluate_restore_approval_gate(
        {**suite, "certified": True, "n24_full_conformance": True}
    )
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
