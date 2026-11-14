"""Marketplace publish queue: publish → list → approve/reject → listed visibility."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.harness.knowledge.skill_marketplace import SkillMarketplace


@pytest.fixture()
def mkt(tmp_path: Path) -> SkillMarketplace:
    return SkillMarketplace(db_path=str(tmp_path / "marketplace.db"))


def test_publish_list_approve_listed(mkt: SkillMarketplace):
    row = mkt.create_submission(
        submission_id="sub_a1",
        tenant_id="t1",
        skill_id="demo_skill",
        test_result={"ok": True, "score": 1.0},
    )
    assert row["status"] == "pending_review"
    assert row["skill_id"] == "demo_skill"

    pending = mkt.list_submissions(status="pending_review")
    assert any(r["submission_id"] == "sub_a1" for r in pending)

    decided = mkt.decide_submission("sub_a1", decision="approve", decided_by="admin")
    assert decided["status"] == "approved"
    assert decided["listed"] is True

    listed = mkt.list_listed_skills()
    assert any(r["skill_id"] == "demo_skill" for r in listed)


def test_reject_does_not_list(mkt: SkillMarketplace):
    mkt.create_submission(
        submission_id="sub_b1",
        tenant_id="t1",
        skill_id="reject_me",
        test_result={"ok": False},
    )
    decided = mkt.decide_submission(
        "sub_b1", decision="reject", decided_by="admin", reason="weak_tests"
    )
    assert decided["status"] == "rejected"
    assert decided["listed"] is False
    assert decided["reason"] == "weak_tests"
    assert mkt.list_listed_skills() == []


def test_decide_unknown_and_non_pending(mkt: SkillMarketplace):
    with pytest.raises(KeyError):
        mkt.decide_submission("missing", decision="approve")
    mkt.create_submission(
        submission_id="sub_c1",
        tenant_id="t1",
        skill_id="once",
        test_result={},
    )
    mkt.decide_submission("sub_c1", decision="approve")
    with pytest.raises(ValueError):
        mkt.decide_submission("sub_c1", decision="reject")


def test_core_facade_marketplace_wrappers(tmp_path: Path):
    """CoreFacade thin wrappers persist via SkillMarketplace (no harness import in platform)."""
    try:
        from core.api import core_facade as facade
    except TypeError as exc:
        # protocol.py uses dataclass(kw_only=True) — needs Python 3.10+
        if "kw_only" in str(exc):
            pytest.skip("core_facade import requires Python>=3.10")
        raise

    db = str(tmp_path / "facade_mkt.db")
    row = facade.marketplace_create_submission(
        submission_id="sub_f1",
        tenant_id="t1",
        skill_id="facade_skill",
        test_result={"ok": True},
        db_path=db,
    )
    assert row["status"] == "pending_review"
    listed = facade.marketplace_list_submissions(status="pending_review", db_path=db)
    assert any(r["submission_id"] == "sub_f1" for r in listed)
    approved = facade.marketplace_decide_submission(
        "sub_f1", decision="approve", decided_by="admin", db_path=db
    )
    assert approved["status"] == "approved"
    assert any(
        r["skill_id"] == "facade_skill"
        for r in facade.marketplace_list_listed_skills(db_path=db)
    )
