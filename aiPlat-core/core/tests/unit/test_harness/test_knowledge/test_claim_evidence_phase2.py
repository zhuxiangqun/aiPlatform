"""F2：N03 Claim 证据硬门 + 冲突记录（certified 恒 false）。"""
from __future__ import annotations

import pytest

from core.harness.knowledge_pipeline.fact_ledger import (
    FactLedger,
    FactLedgerError,
    evaluate_claim_evidence_gate,
    run_claim_evidence_suite,
)
from core.harness.knowledge_pipeline.source_policy import register_source_policy


@pytest.fixture
async def ledger(tmp_path):
    store = FactLedger(
        db_path=str(tmp_path / "fact_ledger.sqlite3"),
        raw_dir=tmp_path / "raw",
    )
    await store.initialize()
    return store


async def _src(ledger: FactLedger, tenant_id: str = "t1"):
    return await ledger.register_source(
        tenant_id=tenant_id,
        collection_id="c1",
        kind="file",
        uri="file://n03/ok.txt",
        content=b"n03-ok",
        connector="n03",
    )


@pytest.mark.asyncio
async def test_published_without_evidence_rejected(ledger: FactLedger):
    with pytest.raises(FactLedgerError, match="published requires non-empty evidence"):
        await ledger.put_claim(
            tenant_id="t1",
            collection_id="c1",
            text="no evidence",
            evidence=[],
            source_policy="p1",
            extractor_version="t",
            review_status="published",
            confidence=0.5,
        )


@pytest.mark.asyncio
async def test_published_with_evidence_ok(ledger: FactLedger):
    src = await _src(ledger)
    claim = await ledger.put_claim(
        tenant_id="t1",
        collection_id="c1",
        text="ok claim",
        evidence=[
            {
                "source_id": src["source_id"],
                "locator": "x",
                "quote": "ok",
                "fetched_at": src["fetched_at"],
            }
        ],
        source_policy="p1",
        extractor_version="t",
        review_status="published",
        confidence=0.9,
        conflict_key="topic.a",
    )
    got = await ledger.get_claim(claim["claim_id"], tenant_id="t1")
    assert got is not None
    assert got["text"] == "ok claim"
    assert got["conflict_key"] == "topic.a"


@pytest.mark.asyncio
async def test_claim_conflict_recorded(ledger: FactLedger):
    src = await _src(ledger)
    ev = [
        {
            "source_id": src["source_id"],
            "locator": "x",
            "quote": "q",
            "fetched_at": src["fetched_at"],
        }
    ]
    a = await ledger.put_claim(
        tenant_id="t1",
        collection_id="c1",
        text="state=locked",
        evidence=ev,
        source_policy="p1",
        extractor_version="t",
        review_status="published",
        confidence=0.8,
        conflict_key="door.state",
    )
    b = await ledger.put_claim(
        tenant_id="t1",
        collection_id="c1",
        text="state=unlocked",
        evidence=ev,
        source_policy="p1",
        extractor_version="t",
        review_status="published",
        confidence=0.7,
        conflict_key="door.state",
    )
    assert a.get("conflict_id") is None
    assert b.get("conflict_id")
    conflicts = await ledger.list_claim_conflicts(
        tenant_id="t1", collection_id="c1", conflict_key="door.state"
    )
    assert len(conflicts) >= 1
    assert conflicts[0]["status"] == "open"
    assert set(conflicts[0]["claim_ids"]) >= {a["claim_id"], b["claim_id"]}


@pytest.mark.asyncio
async def test_enforce_write_gates_unknown_policy(ledger: FactLedger, tmp_path):
    src = await _src(ledger)
    pol_db = str(tmp_path / "source_policy.sqlite3")
    with pytest.raises(FactLedgerError, match="unknown source_policy"):
        await ledger.put_claim(
            tenant_id="t1",
            collection_id="c1",
            text="gated",
            evidence=[
                {
                    "source_id": src["source_id"],
                    "locator": "x",
                    "quote": "q",
                    "fetched_at": src["fetched_at"],
                }
            ],
            source_policy="missing_policy",
            extractor_version="t",
            review_status="published",
            confidence=0.5,
            enforce_write_gates=True,
            source_policy_db_path=pol_db,
        )
    register_source_policy(
        tenant_id="t1",
        policy_id="ok_policy",
        authority="system",
        freshness={"valid_days": 30},
        scope=["n03"],
        license="internal",
        trust="high",
        conflict_rule="prefer_human_review",
        db_path=pol_db,
    )
    ok = await ledger.put_claim(
        tenant_id="t1",
        collection_id="c1",
        text="gated ok",
        evidence=[
            {
                "source_id": src["source_id"],
                "locator": "x",
                "quote": "q",
                "fetched_at": src["fetched_at"],
            }
        ],
        source_policy="ok_policy",
        extractor_version="t",
        review_status="published",
        confidence=0.5,
        enforce_write_gates=True,
        source_policy_db_path=pol_db,
    )
    assert ok["claim_id"]


@pytest.mark.asyncio
async def test_suite_and_gate_honesty():
    suite = await run_claim_evidence_suite()
    assert suite["ok"] is True
    assert suite["certified"] is False
    assert suite["n03_full_conformance"] is False
    gate = evaluate_claim_evidence_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["n03_full_conformance"] is False
    bad = dict(suite)
    bad["certified"] = True
    honesty = evaluate_claim_evidence_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
