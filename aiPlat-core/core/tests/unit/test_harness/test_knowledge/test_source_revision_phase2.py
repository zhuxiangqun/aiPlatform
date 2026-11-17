"""H2：N24 Source Revision 最小账本（certified 恒 false）。"""
from __future__ import annotations

import pytest

from core.harness.knowledge_pipeline.fact_ledger import (
    FactLedger,
    FactLedgerError,
    evaluate_source_revision_gate,
    run_source_revision_suite,
)


@pytest.fixture
async def ledger(tmp_path):
    store = FactLedger(
        db_path=str(tmp_path / "fact_ledger.sqlite3"),
        raw_dir=tmp_path / "raw",
    )
    await store.initialize()
    return store


async def _seed_source(
    ledger: FactLedger,
    *,
    content: bytes,
    uri: str,
    revision: int = 1,
    source_id: str | None = None,
):
    return await ledger.register_source(
        tenant_id="t1",
        collection_id="c1",
        kind="file",
        uri=uri,
        content=content,
        connector="n24",
        source_id=source_id,
        revision=revision,
        revision_actor="test",
        revision_reason="test",
    )


@pytest.mark.asyncio
async def test_overwrite_without_revision_bump_rejected(ledger: FactLedger):
    src = await _seed_source(
        ledger, content=b"v1", uri="file://n24/v1.txt", revision=1
    )
    with pytest.raises(FactLedgerError, match="revision bump"):
        await _seed_source(
            ledger,
            content=b"v2",
            uri="file://n24/v2.txt",
            revision=1,
            source_id=src["source_id"],
        )


@pytest.mark.asyncio
async def test_revision_archived_on_update(ledger: FactLedger):
    src = await _seed_source(
        ledger, content=b"v1", uri="file://n24/v1.txt", revision=1
    )
    sid = src["source_id"]
    updated = await _seed_source(
        ledger,
        content=b"v2",
        uri="file://n24/v2.txt",
        revision=2,
        source_id=sid,
    )
    assert updated["revision"] == 2
    hist = await ledger.list_source_revisions(sid, tenant_id="t1")
    archived = [h for h in hist if not h.get("is_head")]
    assert len(archived) == 1
    assert archived[0]["revision"] == 1
    assert archived[0]["snapshot"]["sha256"] == src["sha256"]
    assert hist[-1]["is_head"] is True
    assert hist[-1]["snapshot"]["sha256"] == updated["sha256"]


@pytest.mark.asyncio
async def test_get_and_diff_source_revisions(ledger: FactLedger):
    src = await _seed_source(
        ledger, content=b"v1", uri="file://n24/v1.txt", revision=1
    )
    sid = src["source_id"]
    updated = await _seed_source(
        ledger,
        content=b"v2",
        uri="file://n24/v2.txt",
        revision=2,
        source_id=sid,
    )
    old = await ledger.get_source_at_revision(sid, tenant_id="t1", revision=1)
    new = await ledger.get_source_at_revision(sid, tenant_id="t1", revision=2)
    assert old is not None and old["sha256"] == src["sha256"]
    assert new is not None and new["sha256"] == updated["sha256"]
    diff = await ledger.diff_source_revisions(
        sid, tenant_id="t1", from_revision=1, to_revision=2
    )
    assert "sha256" in diff["changed"]
    assert diff["changed"]["sha256"]["from"] == src["sha256"]
    assert diff["changed"]["sha256"]["to"] == updated["sha256"]
    assert "uri" in diff["changed"]


@pytest.mark.asyncio
async def test_same_content_idempotent(ledger: FactLedger):
    src = await _seed_source(
        ledger, content=b"same", uri="file://n24/same.txt", revision=1
    )
    again = await _seed_source(
        ledger,
        content=b"same",
        uri="file://n24/same.txt",
        revision=1,
        source_id=src["source_id"],
    )
    assert again["revision"] == 1
    assert again["sha256"] == src["sha256"]
    hist = await ledger.list_source_revisions(src["source_id"], tenant_id="t1")
    assert len([h for h in hist if not h.get("is_head")]) == 0


@pytest.mark.asyncio
async def test_suite_and_gate_honesty():
    suite = await run_source_revision_suite()
    assert suite["ok"] is True
    assert suite["certified"] is False
    assert suite["n24_full_conformance"] is False
    gate = evaluate_source_revision_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    honesty = evaluate_source_revision_gate(
        {**suite, "certified": True, "n24_full_conformance": True}
    )
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
