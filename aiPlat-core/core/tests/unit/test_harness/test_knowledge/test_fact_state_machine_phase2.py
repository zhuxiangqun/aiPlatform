"""W3 / N12 Fact 状态机最小切片测试。"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.harness.knowledge_pipeline.fact_ledger import FactLedger
from core.harness.knowledge_pipeline.fact_state_machine import (
    FactStateMachineError,
    _assert_transition_allowed,
    evaluate_fact_state_gate,
    _is_transition_allowed,
    list_fact_transitions,
    transition_claim_status_pure,
    transition_fact_lifecycle,
    transition_fact_review,
    validate_sequence,
)


@pytest.fixture
def sm_db(tmp_path: Path) -> str:
    return str(tmp_path / "fact_state.sqlite3")


@pytest.fixture
async def ledger(tmp_path: Path) -> FactLedger:
    lg = FactLedger(
        db_path=str(tmp_path / "facts.sqlite3"),
        raw_dir=tmp_path / "raw",
    )
    await lg.initialize()
    return lg


def test_review_and_lifecycle_edges():
    assert _is_transition_allowed("fact_review", "draft", "reviewed")
    assert not _is_transition_allowed("fact_review", "draft", "published")
    assert not _is_transition_allowed("fact_review", "published", "draft")
    assert _is_transition_allowed("fact_lifecycle", "active", "superseded")
    assert not _is_transition_allowed("fact_lifecycle", "superseded", "active")
    assert _is_transition_allowed("claim_status", "accepted", "contested")
    assert not _is_transition_allowed("claim_status", "retracted", "accepted")
    assert validate_sequence("fact_review", ["draft", "reviewed", "published"])
    assert not validate_sequence("fact_review", ["draft", "published"])
    with pytest.raises(FactStateMachineError, match="illegal"):
        _assert_transition_allowed("fact_review", "draft", "published")


@pytest.mark.asyncio
async def test_transition_requires_actor_reason_and_audit(
    ledger: FactLedger, sm_db: str, tmp_path: Path
):
    from core.harness.knowledge_pipeline.source_policy import register_source_policy

    sp_db = str(tmp_path / "source_policy.sqlite3")
    register_source_policy(
        tenant_id="t1",
        policy_id="p1",
        authority="primary",
        freshness={"valid_days": 30},
        scope=["test"],
        license="internal",
        trust="high",
        conflict_rule="prefer_newer_primary_then_human_review",
        db_path=sp_db,
    )
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="kb",
        kind="doc",
        uri="mem://n12",
        content=b"n12",
        connector="test",
    )
    ev = [{"source_id": src["source_id"], "locator": "p.1", "quote": "x"}]
    fact = await ledger.put_fact(
        tenant_id="t1",
        collection_id="kb",
        subject="ent-a",
        predicate="status",
        object="open",
        evidence=ev,
        source_policy="p1",
        extractor_version="e1",
        review_status="draft",
        confidence=0.9,
        fact_id="fact-n12",
        status="active",
        source_policy_db_path=sp_db,
    )
    with pytest.raises(FactStateMachineError, match="actor"):
        await transition_fact_review(
            ledger,
            fact_id=fact["fact_id"],
            tenant_id="t1",
            to_status="reviewed",
            actor="",
            reason="ok",
            db_path=sm_db,
        )
    with pytest.raises(FactStateMachineError, match="illegal"):
        await transition_fact_review(
            ledger,
            fact_id=fact["fact_id"],
            tenant_id="t1",
            to_status="published",
            actor="reviewer-1",
            reason="skip",
            db_path=sm_db,
        )
    mid = await transition_fact_review(
        ledger,
        fact_id=fact["fact_id"],
        tenant_id="t1",
        to_status="reviewed",
        actor="reviewer-1",
        reason="looks good",
        db_path=sm_db,
    )
    assert mid["fact"]["review_status"] == "reviewed"
    assert mid["transition"]["actor"] == "reviewer-1"
    assert mid["fact"]["revision"] == 2

    published = await transition_fact_review(
        ledger,
        fact_id=fact["fact_id"],
        tenant_id="t1",
        to_status="published",
        actor="reviewer-1",
        reason="approve publish",
        db_path=sm_db,
        source_policy_db_path=sp_db,
        role="reviewer",
    )
    assert published["fact"]["review_status"] == "published"

    retired = await transition_fact_lifecycle(
        ledger,
        fact_id=fact["fact_id"],
        tenant_id="t1",
        to_status="retracted",
        actor="reviewer-1",
        reason="policy change",
        db_path=sm_db,
    )
    assert retired["fact"]["status"] == "retracted"
    still = await ledger.get_fact("fact-n12", tenant_id="t1")
    assert still is not None
    assert still["status"] == "retracted"

    audits = list_fact_transitions(
        tenant_id="t1", record_id="fact-n12", db_path=sm_db
    )
    assert len(audits) >= 3
    assert all(a["actor"] and a["reason"] for a in audits)


def test_claim_status_and_gate(sm_db: str):
    audit = transition_claim_status_pure(
        from_status="accepted",
        to_status="contested",
        actor="rev",
        reason="conflict",
        claim_id="c1",
        tenant_id="t1",
        db_path=sm_db,
        revision=2,
    )
    assert audit["machine"] == "claim_status"
    with pytest.raises(FactStateMachineError):
        transition_claim_status_pure(
            from_status="retracted",
            to_status="accepted",
            actor="rev",
            reason="bad",
            claim_id="c1",
            tenant_id="t1",
            db_path=sm_db,
        )
    gate = evaluate_fact_state_gate(
        checks={
            "review_edges": True,
            "lifecycle_edges": True,
            "claim_edges": True,
            "actor_reason_audit": True,
            "skip_review_forbidden": True,
            "retracted_not_deleted": True,
        }
    )
    assert gate["pass"] is True
    assert gate["certified"] is False
    assert gate["n12_full_conformance"] is False
    empty = evaluate_fact_state_gate()
    assert empty["pass"] is False
