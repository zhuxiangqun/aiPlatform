"""W3 写入硬门加深：裸 put_fact 强制策略/冲突/状态边。"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.harness.knowledge_pipeline.fact_ledger import FactLedger, FactLedgerError
from core.harness.knowledge_pipeline.fact_state_machine import transition_fact_review
from core.harness.knowledge_pipeline.source_policy import (
    adjudicate_conflict,
    register_source_policy,
    scan_and_record_conflicts,
)


def _reg(sp_db: str, tenant_id: str = "t1", policy_id: str = "pol-a") -> None:
    register_source_policy(
        tenant_id=tenant_id,
        policy_id=policy_id,
        authority="primary",
        freshness={"valid_days": 30},
        scope=["test"],
        license="internal",
        trust="high",
        conflict_rule="prefer_newer_primary_then_human_review",
        db_path=sp_db,
    )


@pytest.fixture
async def ledger(tmp_path: Path) -> FactLedger:
    lg = FactLedger(
        db_path=str(tmp_path / "facts.sqlite3"),
        raw_dir=tmp_path / "raw",
    )
    await lg.initialize()
    return lg


@pytest.mark.asyncio
async def test_put_fact_rejects_unknown_policy(ledger: FactLedger, tmp_path: Path):
    sp_db = str(tmp_path / "sp.sqlite3")
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="kb",
        kind="doc",
        uri="mem://g1",
        content=b"x",
        connector="t",
    )
    with pytest.raises(FactLedgerError, match="unknown source_policy"):
        await ledger.put_fact(
            tenant_id="t1",
            collection_id="kb",
            subject="a",
            predicate="p",
            object="1",
            evidence=[{"source_id": src["source_id"], "locator": "1", "quote": "x"}],
            source_policy="missing",
            extractor_version="e1",
            review_status="draft",
            confidence=0.5,
            source_policy_db_path=sp_db,
        )


@pytest.mark.asyncio
async def test_put_fact_rejects_direct_published(ledger: FactLedger, tmp_path: Path):
    sp_db = str(tmp_path / "sp.sqlite3")
    _reg(sp_db)
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="kb",
        kind="doc",
        uri="mem://g2",
        content=b"x",
        connector="t",
    )
    with pytest.raises(FactLedgerError, match="cannot be published"):
        await ledger.put_fact(
            tenant_id="t1",
            collection_id="kb",
            subject="a",
            predicate="p",
            object="1",
            evidence=[{"source_id": src["source_id"], "locator": "1", "quote": "x"}],
            source_policy="pol-a",
            extractor_version="e1",
            review_status="published",
            confidence=0.5,
            source_policy_db_path=sp_db,
        )


@pytest.mark.asyncio
async def test_put_fact_rejects_status_change_without_transition(
    ledger: FactLedger, tmp_path: Path
):
    sp_db = str(tmp_path / "sp.sqlite3")
    _reg(sp_db)
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="kb",
        kind="doc",
        uri="mem://g3",
        content=b"x",
        connector="t",
    )
    ev = [{"source_id": src["source_id"], "locator": "1", "quote": "x"}]
    fact = await ledger.put_fact(
        tenant_id="t1",
        collection_id="kb",
        subject="a",
        predicate="p",
        object="1",
        evidence=ev,
        source_policy="pol-a",
        extractor_version="e1",
        review_status="draft",
        confidence=0.5,
        fact_id="f-skip",
        source_policy_db_path=sp_db,
    )
    with pytest.raises(FactLedgerError, match="transition API"):
        await ledger.put_fact(
            tenant_id="t1",
            collection_id="kb",
            subject="a",
            predicate="p",
            object="1",
            evidence=ev,
            source_policy="pol-a",
            extractor_version="e1",
            review_status="published",
            confidence=0.5,
            fact_id=fact["fact_id"],
            source_policy_db_path=sp_db,
        )


@pytest.mark.asyncio
async def test_transition_publish_blocked_by_open_conflict(
    ledger: FactLedger, tmp_path: Path
):
    sp_db = str(tmp_path / "sp.sqlite3")
    _reg(sp_db)
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="kb",
        kind="doc",
        uri="mem://g4",
        content=b"x",
        connector="t",
    )
    ev = [{"source_id": src["source_id"], "locator": "1", "quote": "x"}]
    f1 = await ledger.put_fact(
        tenant_id="t1",
        collection_id="kb",
        subject="ent",
        predicate="status",
        object="open",
        evidence=ev,
        source_policy="pol-a",
        extractor_version="e1",
        review_status="draft",
        confidence=0.9,
        fact_id="f-open",
        source_policy_db_path=sp_db,
    )
    await ledger.put_fact(
        tenant_id="t1",
        collection_id="kb",
        subject="ent",
        predicate="status",
        object="closed",
        evidence=ev,
        source_policy="pol-a",
        extractor_version="e1",
        review_status="draft",
        confidence=0.8,
        fact_id="f-closed",
        source_policy_db_path=sp_db,
    )
    conflicts = await scan_and_record_conflicts(
        ledger,
        tenant_id="t1",
        collection_id="kb",
        subject="ent",
        predicate="status",
        db_path=sp_db,
    )
    assert conflicts and conflicts[0]["status"] == "open"
    await transition_fact_review(
        ledger,
        fact_id=f1["fact_id"],
        tenant_id="t1",
        to_status="reviewed",
        actor="r1",
        reason="ok",
        source_policy_db_path=sp_db,
    )
    from core.harness.knowledge_pipeline.fact_state_machine import FactStateMachineError

    with pytest.raises(FactStateMachineError, match="unresolved"):
        await transition_fact_review(
            ledger,
            fact_id=f1["fact_id"],
            tenant_id="t1",
            to_status="published",
            actor="r1",
            reason="publish",
            source_policy_db_path=sp_db,
            role="reviewer",
        )
    adjudicate_conflict(
        conflict_id=conflicts[0]["conflict_id"],
        tenant_id="t1",
        actor="r1",
        reason="pick open",
        accepted_fact_id="f-open",
        db_path=sp_db,
    )
    published = await transition_fact_review(
        ledger,
        fact_id=f1["fact_id"],
        tenant_id="t1",
        to_status="published",
        actor="r1",
        reason="publish",
        source_policy_db_path=sp_db,
        role="reviewer",
    )
    assert published["fact"]["review_status"] == "published"
