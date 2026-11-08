"""P1.1 human_review queue: draft → in_review → reviewed|rejected (no freeze)."""
from __future__ import annotations

import pytest

from core.apps.eval.service.case_factory import (
    generate_cases_from_template,
    publish_draft_workspace_pack,
)
from core.apps.eval.service.case_review_queue import (
    CaseReviewError,
    enqueue_pack_for_review,
    list_review_queue,
    submit_review_decision,
)


def _draft(tmp_path, monkeypatch, pack_id="ws.review.demo", version="0.1.0"):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    cases = generate_cases_from_template(
        {"prompt": "say ok", "rubric": {"type": "lexical"}, "category": "normal"},
        variants=[{"case_id": "r1"}],
    )
    out = publish_draft_workspace_pack(
        pack_id=pack_id,
        version=version,
        cases=cases,
        workspace_id="ws-a",
        caller_workspace_id="ws-a",
    )
    assert out["registry"]["status"] == "draft"
    return out


def test_enqueue_list_approve(tmp_path, monkeypatch):
    _draft(tmp_path, monkeypatch)
    enq = enqueue_pack_for_review(
        pack_id="ws.review.demo",
        version="0.1.0",
        workspace_id="ws-a",
    )
    assert enq["status"] == "in_review"
    assert enq["claim_eligible"] is False
    q = list_review_queue(workspace_id="ws-a", statuses=["in_review"])
    assert q["n"] == 1
    assert q["items"][0]["pack_id"] == "ws.review.demo"
    decided = submit_review_decision(
        pack_id="ws.review.demo",
        version="0.1.0",
        workspace_id="ws-a",
        decision="approve",
        reviewer="alice",
        notes="looks fine",
    )
    assert decided["status"] == "reviewed"
    assert decided["frozen"] is False
    assert decided["claim_eligible"] is False
    assert decided["accuracy_claim"] is False
    q2 = list_review_queue(workspace_id="ws-a", statuses=["in_review"])
    assert q2["n"] == 0


def test_reject_and_reenqueue(tmp_path, monkeypatch):
    _draft(tmp_path, monkeypatch, pack_id="ws.review.reject", version="0.2.0")
    enqueue_pack_for_review(
        pack_id="ws.review.reject", version="0.2.0", workspace_id="ws-a"
    )
    rejected = submit_review_decision(
        pack_id="ws.review.reject",
        version="0.2.0",
        workspace_id="ws-a",
        decision="reject",
        reviewer="bob",
    )
    assert rejected["status"] == "rejected"
    enq2 = enqueue_pack_for_review(
        pack_id="ws.review.reject", version="0.2.0", workspace_id="ws-a"
    )
    assert enq2["status"] == "in_review"


def test_cannot_decide_unless_in_review(tmp_path, monkeypatch):
    _draft(tmp_path, monkeypatch, pack_id="ws.review.early", version="1.0.0")
    with pytest.raises(CaseReviewError, match="in_review"):
        submit_review_decision(
            pack_id="ws.review.early",
            version="1.0.0",
            workspace_id="ws-a",
            decision="approve",
        )


def test_acl_cross_workspace(tmp_path, monkeypatch):
    _draft(tmp_path, monkeypatch, pack_id="ws.review.acl", version="1.0.0")
    with pytest.raises(Exception, match="ACL deny"):
        enqueue_pack_for_review(
            pack_id="ws.review.acl",
            version="1.0.0",
            workspace_id="ws-a",
            caller_workspace_id="ws-b",
        )
