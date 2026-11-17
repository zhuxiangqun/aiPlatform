"""G2：N24 Fact Revision 最小账本（certified 恒 false）。"""
from __future__ import annotations

import pytest

from core.harness.knowledge_pipeline.fact_ledger import (
    FactLedger,
    FactLedgerError,
    evaluate_fact_revision_gate,
    run_fact_revision_suite,
)


@pytest.fixture
async def ledger(tmp_path):
    store = FactLedger(
        db_path=str(tmp_path / "fact_ledger.sqlite3"),
        raw_dir=tmp_path / "raw",
    )
    await store.initialize()
    return store


async def _seed_fact(ledger: FactLedger, *, object_value: str = "locked", revision: int = 1, fact_id: str | None = None):
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="c1",
        kind="file",
        uri=f"file://n24/{object_value}.txt",
        content=f"n24-{object_value}".encode(),
        connector="n24",
        source_id=f"src-{object_value}" if fact_id is None else None,
    )
    return await ledger.put_fact(
        tenant_id="t1",
        collection_id="c1",
        subject="Door:d1",
        predicate="state",
        object=object_value,
        evidence=[
            {
                "source_id": src["source_id"],
                "locator": "x",
                "quote": object_value,
                "fetched_at": src["fetched_at"],
            }
        ],
        source_policy="n24",
        extractor_version="t",
        review_status="draft",
        confidence=0.5,
        fact_id=fact_id,
        revision=revision,
        enforce_write_gates=False,
    )


@pytest.mark.asyncio
async def test_overwrite_without_revision_bump_rejected(ledger: FactLedger):
    fact = await _seed_fact(ledger, object_value="locked", revision=1)
    with pytest.raises(FactLedgerError, match="revision bump"):
        await _seed_fact(
            ledger,
            object_value="unlocked",
            revision=1,
            fact_id=fact["fact_id"],
        )


@pytest.mark.asyncio
async def test_revision_archived_on_update(ledger: FactLedger):
    fact = await _seed_fact(ledger, object_value="locked", revision=1)
    fid = fact["fact_id"]
    updated = await _seed_fact(
        ledger, object_value="unlocked", revision=2, fact_id=fid
    )
    assert updated["revision"] == 2
    hist = await ledger.list_fact_revisions(fid, tenant_id="t1")
    archived = [h for h in hist if not h.get("is_head")]
    assert len(archived) == 1
    assert archived[0]["revision"] == 1
    assert archived[0]["snapshot"]["object"] == "locked"
    assert hist[-1]["is_head"] is True
    assert hist[-1]["snapshot"]["object"] == "unlocked"


@pytest.mark.asyncio
async def test_get_and_diff_revisions(ledger: FactLedger):
    fact = await _seed_fact(ledger, object_value="locked", revision=1)
    fid = fact["fact_id"]
    await _seed_fact(ledger, object_value="unlocked", revision=2, fact_id=fid)
    old = await ledger.get_fact_at_revision(fid, tenant_id="t1", revision=1)
    new = await ledger.get_fact_at_revision(fid, tenant_id="t1", revision=2)
    assert old is not None and old["object"] == "locked"
    assert new is not None and new["object"] == "unlocked"
    diff = await ledger.diff_fact_revisions(
        fid, tenant_id="t1", from_revision=1, to_revision=2
    )
    assert "object" in diff["changed"]
    assert diff["changed"]["object"]["from"] == "locked"
    assert diff["changed"]["object"]["to"] == "unlocked"


@pytest.mark.asyncio
async def test_suite_and_gate_honesty():
    suite = await run_fact_revision_suite()
    assert suite["ok"] is True
    assert suite["certified"] is False
    assert suite["n24_full_conformance"] is False
    gate = evaluate_fact_revision_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    honesty = evaluate_fact_revision_gate(
        {**suite, "certified": True, "n24_full_conformance": True}
    )
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
