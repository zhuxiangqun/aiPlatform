"""W3 / N04 来源策略与冲突裁决最小切片测试。"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.harness.knowledge_pipeline.fact_ledger import FactLedger
from core.harness.knowledge_pipeline.source_policy import (
    SourcePolicyError,
    adjudicate_conflict,
    assert_publish_allowed,
    detect_object_conflicts,
    evaluate_source_policy_gate,
    put_fact_with_source_policy,
    record_conflict,
    register_source_policy,
    scan_and_record_conflicts,
)


def _policy_kwargs(**over):
    base = {
        "authority": "primary",
        "freshness": {"valid_days": 365},
        "scope": ["refund_policy"],
        "license": "company-internal",
        "trust": "high",
        "conflict_rule": "prefer_newer_primary_then_human_review",
    }
    base.update(over)
    return base


@pytest.fixture
def sp_db(tmp_path: Path) -> str:
    return str(tmp_path / "source_policy.sqlite3")


@pytest.mark.asyncio
async def test_policy_register_and_forbid_fixed_layer(sp_db: str):
    rec = register_source_policy(
        tenant_id="t1",
        policy_id="primary_2026",
        db_path=sp_db,
        **_policy_kwargs(),
    )
    assert rec["policy_id"] == "primary_2026"
    assert rec["authority"] == "primary"
    with pytest.raises(SourcePolicyError, match="fixed"):
        register_source_policy(
            tenant_id="t1",
            policy_id="bad",
            db_path=sp_db,
            **_policy_kwargs(conflict_rule="raw_gt_kg_gt_wiki"),
        )


def test_detect_conflict_no_autopick():
    facts = [
        {
            "fact_id": "f1",
            "subject": "ent-a",
            "predicate": "status",
            "object": "open",
            "status": "active",
        },
        {
            "fact_id": "f2",
            "subject": "ent-a",
            "predicate": "status",
            "object": "closed",
            "status": "active",
        },
    ]
    cands = detect_object_conflicts(facts)
    assert len(cands) == 1
    assert cands[0]["auto_winner"] is None
    assert set(cands[0]["objects"]) == {"open", "closed"}


@pytest.mark.asyncio
async def test_adjudicate_and_publish_gate(sp_db: str, tmp_path: Path):
    register_source_policy(
        tenant_id="t1",
        policy_id="primary_2026",
        db_path=sp_db,
        **_policy_kwargs(),
    )
    ledger = FactLedger(
        db_path=str(tmp_path / "facts.sqlite3"),
        raw_dir=tmp_path / "raw",
    )
    await ledger.initialize()
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="kb",
        kind="doc",
        uri="mem://a",
        content=b"status open",
        connector="test",
    )
    ev = [{"source_id": src["source_id"], "locator": "p.1", "quote": "open"}]
    f1 = await ledger.put_fact(
        tenant_id="t1",
        collection_id="kb",
        subject="ent-a",
        predicate="status",
        object="open",
        evidence=ev,
        source_policy="primary_2026",
        extractor_version="e1",
        review_status="draft",
        confidence=0.9,
        fact_id="fact-open",
        source_policy_db_path=sp_db,
    )
    f2 = await ledger.put_fact(
        tenant_id="t1",
        collection_id="kb",
        subject="ent-a",
        predicate="status",
        object="closed",
        evidence=ev,
        source_policy="primary_2026",
        extractor_version="e1",
        review_status="draft",
        confidence=0.8,
        fact_id="fact-closed",
        source_policy_db_path=sp_db,
    )
    conflicts = await scan_and_record_conflicts(
        ledger,
        tenant_id="t1",
        collection_id="kb",
        subject="ent-a",
        predicate="status",
        db_path=sp_db,
    )
    assert len(conflicts) == 1
    assert conflicts[0]["status"] == "open"
    # suggestion may exist but must not auto-resolve
    assert conflicts[0].get("decision") is None

    with pytest.raises(SourcePolicyError, match="unresolved"):
        assert_publish_allowed(
            tenant_id="t1",
            source_policy="primary_2026",
            subject="ent-a",
            predicate="status",
            db_path=sp_db,
        )

    with pytest.raises(SourcePolicyError, match="unresolved"):
        await put_fact_with_source_policy(
            ledger,
            tenant_id="t1",
            collection_id="kb",
            subject="ent-a",
            predicate="status",
            object="open",
            evidence=ev,
            source_policy="primary_2026",
            extractor_version="e1",
            review_status="published",
            confidence=0.9,
            db_path=sp_db,
            fact_id="fact-publish-blocked",
        )

    resolved = adjudicate_conflict(
        conflict_id=conflicts[0]["conflict_id"],
        tenant_id="t1",
        actor="reviewer-1",
        reason="latest official policy",
        accepted_fact_id=f1["fact_id"],
        db_path=sp_db,
    )
    assert resolved["status"] == "resolved"
    assert resolved["decision"]["by"] == "reviewer-1"
    assert resolved["decision"]["accepted_fact_id"] == "fact-open"

    assert_publish_allowed(
        tenant_id="t1",
        source_policy="primary_2026",
        subject="ent-a",
        predicate="status",
        db_path=sp_db,
    )
    published = await put_fact_with_source_policy(
        ledger,
        tenant_id="t1",
        collection_id="kb",
        subject="ent-a",
        predicate="status",
        object="open",
        evidence=ev,
        source_policy="primary_2026",
        extractor_version="e1",
        review_status="published",
        confidence=0.95,
        db_path=sp_db,
        fact_id="fact-open",
        actor="reviewer-1",
        reason="adjudicated publish",
        role="reviewer",
    )
    assert published["review_status"] == "published"
    assert published["fact_id"] == "fact-open"
    assert f2["fact_id"] == "fact-closed"


def test_gate_never_certifies():
    gate = evaluate_source_policy_gate(
        checks={
            "policy_register": True,
            "conflict_detect_no_autopick": True,
            "adjudicate_with_reason": True,
            "publish_blocked_when_open": True,
            "forbid_fixed_layer_order": True,
        }
    )
    assert gate["pass"] is True
    assert gate["certified"] is False
    assert gate["n04_full_conformance"] is False
    empty = evaluate_source_policy_gate()
    assert empty["pass"] is False
    assert empty["certified"] is False


def test_record_conflict_requires_distinct_objects(sp_db: str):
    with pytest.raises(SourcePolicyError, match=">=2 distinct"):
        record_conflict(
            tenant_id="t1",
            collection_id="kb",
            subject="a",
            predicate="p",
            fact_ids=["f1", "f2"],
            objects=["same", "same"],
            db_path=sp_db,
        )
