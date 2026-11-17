"""I1：N24 Revision Restore 程序化恢复（certified 恒 false；非 UI）。"""
from __future__ import annotations

import pytest

from core.harness.knowledge_pipeline.fact_ledger import (
    FactLedger,
    FactLedgerError,
    evaluate_revision_restore_gate,
    run_revision_restore_suite,
)


@pytest.fixture
async def ledger(tmp_path):
    store = FactLedger(
        db_path=str(tmp_path / "fact_ledger.sqlite3"),
        raw_dir=tmp_path / "raw",
    )
    await store.initialize()
    return store


async def _seed_mutated(ledger: FactLedger):
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="c1",
        kind="file",
        uri="file://n24/restore-v1.txt",
        content=b"v1",
        connector="n24",
        source_id="src-restore",
        revision=1,
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
        revision_actor="test",
        revision_reason="mutate",
    )
    claim = await ledger.put_claim(
        tenant_id="t1",
        collection_id="c1",
        text="locked",
        evidence=evidence,
        source_policy="n24",
        extractor_version="t",
        review_status="published",
        confidence=0.5,
        revision=1,
    )
    await ledger.put_claim(
        tenant_id="t1",
        collection_id="c1",
        text="unlocked",
        evidence=evidence,
        source_policy="n24",
        extractor_version="t",
        review_status="published",
        confidence=0.5,
        claim_id=claim["claim_id"],
        revision=2,
        revision_actor="test",
        revision_reason="mutate",
    )
    await ledger.register_source(
        tenant_id="t1",
        collection_id="c1",
        kind="file",
        uri="file://n24/restore-v2.txt",
        content=b"v2",
        connector="n24",
        source_id=src["source_id"],
        revision=2,
        revision_actor="test",
        revision_reason="mutate",
    )
    return src, fact, claim


@pytest.mark.asyncio
async def test_restore_requires_actor_reason(ledger: FactLedger):
    src, fact, _claim = await _seed_mutated(ledger)
    with pytest.raises(FactLedgerError, match="actor and reason"):
        await ledger.restore_fact_at_revision(
            fact["fact_id"],
            tenant_id="t1",
            target_revision=1,
            actor="",
            reason="x",
        )
    with pytest.raises(FactLedgerError, match="actor and reason"):
        await ledger.restore_source_at_revision(
            src["source_id"],
            tenant_id="t1",
            target_revision=1,
            actor="a",
            reason="",
        )


@pytest.mark.asyncio
async def test_restore_missing_revision_rejected(ledger: FactLedger):
    _src, fact, _claim = await _seed_mutated(ledger)
    with pytest.raises(FactLedgerError, match="revision not found"):
        await ledger.restore_fact_at_revision(
            fact["fact_id"],
            tenant_id="t1",
            target_revision=99,
            actor="a",
            reason="missing",
        )


@pytest.mark.asyncio
async def test_restore_fact_claim_source(ledger: FactLedger):
    src, fact, claim = await _seed_mutated(ledger)
    fr = await ledger.restore_fact_at_revision(
        fact["fact_id"],
        tenant_id="t1",
        target_revision=1,
        actor="a",
        reason="restore",
        enforce_write_gates=False,
    )
    assert fr["restored"] is True
    assert fr["fact"]["object"] == "locked"
    assert fr["fact"]["revision"] == 3

    cr = await ledger.restore_claim_at_revision(
        claim["claim_id"],
        tenant_id="t1",
        target_revision=1,
        actor="a",
        reason="restore",
    )
    assert cr["restored"] is True
    assert cr["claim"]["text"] == "locked"
    assert cr["claim"]["revision"] == 3

    sr = await ledger.restore_source_at_revision(
        src["source_id"],
        tenant_id="t1",
        target_revision=1,
        actor="a",
        reason="restore",
    )
    assert sr["restored"] is True
    assert sr["source"]["sha256"] == src["sha256"]
    assert sr["source"]["revision"] == 3


@pytest.mark.asyncio
async def test_restore_idempotent(ledger: FactLedger):
    _src, fact, _claim = await _seed_mutated(ledger)
    await ledger.restore_fact_at_revision(
        fact["fact_id"],
        tenant_id="t1",
        target_revision=1,
        actor="a",
        reason="once",
        enforce_write_gates=False,
    )
    again = await ledger.restore_fact_at_revision(
        fact["fact_id"],
        tenant_id="t1",
        target_revision=1,
        actor="a",
        reason="twice",
        enforce_write_gates=False,
    )
    assert again["idempotent"] is True
    assert again["restored"] is False
    assert again["fact"]["revision"] == 3


@pytest.mark.asyncio
async def test_suite_and_gate_honesty():
    suite = await run_revision_restore_suite()
    assert suite["ok"] is True
    assert suite["certified"] is False
    assert suite["n24_full_conformance"] is False
    gate = evaluate_revision_restore_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    honesty = evaluate_revision_restore_gate(
        {**suite, "certified": True, "n24_full_conformance": True}
    )
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
