"""H1：N24 Claim Revision 最小账本（certified 恒 false）。"""
from __future__ import annotations

import pytest

from core.harness.knowledge_pipeline.fact_ledger import (
    FactLedger,
    FactLedgerError,
    evaluate_claim_revision_gate,
    run_claim_revision_suite,
)


@pytest.fixture
async def ledger(tmp_path):
    store = FactLedger(
        db_path=str(tmp_path / "fact_ledger.sqlite3"),
        raw_dir=tmp_path / "raw",
    )
    await store.initialize()
    return store


async def _seed_claim(
    ledger: FactLedger,
    *,
    text: str,
    revision: int = 1,
    claim_id: str | None = None,
):
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="c1",
        kind="file",
        uri=f"file://n24/{text.replace(' ', '-')}.txt",
        content=f"n24-{text}".encode(),
        connector="n24",
    )
    return await ledger.put_claim(
        tenant_id="t1",
        collection_id="c1",
        text=text,
        evidence=[
            {
                "source_id": src["source_id"],
                "locator": "x",
                "quote": text,
                "fetched_at": src["fetched_at"],
            }
        ],
        source_policy="n24",
        extractor_version="t",
        review_status="published",
        confidence=0.5,
        claim_id=claim_id,
        revision=revision,
    )


@pytest.mark.asyncio
async def test_overwrite_without_revision_bump_rejected(ledger: FactLedger):
    claim = await _seed_claim(ledger, text="locked", revision=1)
    with pytest.raises(FactLedgerError, match="revision bump"):
        await _seed_claim(
            ledger, text="unlocked", revision=1, claim_id=claim["claim_id"]
        )


@pytest.mark.asyncio
async def test_revision_archived_on_update(ledger: FactLedger):
    claim = await _seed_claim(ledger, text="locked", revision=1)
    cid = claim["claim_id"]
    updated = await _seed_claim(
        ledger, text="unlocked", revision=2, claim_id=cid
    )
    assert updated["revision"] == 2
    hist = await ledger.list_claim_revisions(cid, tenant_id="t1")
    archived = [h for h in hist if not h.get("is_head")]
    assert len(archived) == 1
    assert archived[0]["revision"] == 1
    assert archived[0]["snapshot"]["text"] == "locked"
    assert hist[-1]["is_head"] is True
    assert hist[-1]["snapshot"]["text"] == "unlocked"


@pytest.mark.asyncio
async def test_get_and_diff_claim_revisions(ledger: FactLedger):
    claim = await _seed_claim(ledger, text="locked", revision=1)
    cid = claim["claim_id"]
    await _seed_claim(ledger, text="unlocked", revision=2, claim_id=cid)
    old = await ledger.get_claim_at_revision(cid, tenant_id="t1", revision=1)
    new = await ledger.get_claim_at_revision(cid, tenant_id="t1", revision=2)
    assert old is not None and old["text"] == "locked"
    assert new is not None and new["text"] == "unlocked"
    diff = await ledger.diff_claim_revisions(
        cid, tenant_id="t1", from_revision=1, to_revision=2
    )
    assert "text" in diff["changed"]
    assert diff["changed"]["text"]["from"] == "locked"
    assert diff["changed"]["text"]["to"] == "unlocked"


@pytest.mark.asyncio
async def test_suite_and_gate_honesty():
    suite = await run_claim_revision_suite()
    assert suite["ok"] is True
    assert suite["certified"] is False
    assert suite["n24_full_conformance"] is False
    gate = evaluate_claim_revision_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    honesty = evaluate_claim_revision_gate(
        {**suite, "certified": True, "n24_full_conformance": True}
    )
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
