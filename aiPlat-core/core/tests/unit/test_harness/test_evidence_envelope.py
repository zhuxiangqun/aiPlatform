"""Evidence Envelope — no fake confirmed without measured evidence."""
from __future__ import annotations

from core.harness.meta.evidence_envelope import (
    allow_release_block,
    attach_envelopes_to_issues,
    envelope_from_review_issue,
    evidence_item,
    normalize_envelope,
    summarize_envelopes,
    validate_envelope,
)


def test_confirmed_without_evidence_demotes():
    v = validate_envelope(
        {
            "status": "confirmed",
            "confidence": "derived",
            "evidence": [],
            "limitations": ["x"],
        },
        demote=True,
    )
    assert v.ok
    assert v.envelope["status"] == "suspected"
    assert "confirmed→suspected" in v.demotions


def test_confirmed_measured_with_evidence_ok():
    v = validate_envelope(
        {
            "status": "confirmed",
            "confidence": "measured",
            "evidence": [evidence_item(type="test_result", ref="pytest::test_x")],
            "limitations": ["unit scope only"],
            "next_check": "",
        },
        demote=True,
    )
    assert v.ok
    assert v.envelope["status"] == "confirmed"
    assert not v.demotions


def test_blocked_requires_limitations():
    v = validate_envelope(
        {
            "status": "blocked",
            "confidence": "measured",
            "evidence": [evidence_item(type="command", ref="arch_guard")],
            "limitations": [],
        },
        demote=True,
    )
    assert v.envelope["status"] == "suspected"
    assert any("blocked→suspected" in d for d in v.demotions)


def test_speculative_cannot_confirm():
    v = validate_envelope(
        {
            "status": "confirmed",
            "confidence": "speculative",
            "evidence": [evidence_item(type="log", ref="guess")],
            "limitations": ["hunch"],
        },
        demote=True,
    )
    # first demote confirmed→suspected due to not measured, or speculative rule
    assert v.envelope["status"] in ("suspected", "unverified")
    assert v.envelope["status"] != "confirmed"


def test_derived_cannot_sole_block_release():
    env = envelope_from_review_issue(
        file="a.py", line=10, description="maybe bug", engine="reasoning"
    )
    ok, reason = allow_release_block(env)
    assert not ok
    assert reason == "derived_watch_only"
    assert env["confidence"] == "derived"
    assert env["status"] == "suspected"


def test_attach_envelopes_strips_fake_confirmed():
    issues = [
        {
            "file": "x.py",
            "line": 1,
            "severity": "P0",
            "description": "sql inject",
            "evidence_envelope": {
                "status": "confirmed",
                "confidence": "derived",
                "evidence": [],
                "limitations": [],
            },
        }
    ]
    out = attach_envelopes_to_issues(issues)
    assert out[0]["evidence_envelope"]["status"] != "confirmed"
    assert out[0]["envelope_ok"] is True
    summary = summarize_envelopes(out)
    assert summary["confirmed_count"] == 0
    assert summary["suspected_count"] >= 1


def test_normalize_preserves_canonical_keys():
    env = normalize_envelope({"status": "SUSPECTED", "confidence": "Derived", "evidence": "bad"})
    assert env["status"] == "suspected"
    assert env["confidence"] == "derived"
    assert env["evidence"] == []


def test_autoreview_report_attaches_derived_envelopes():
    from core.engine.skills.autoreview.review_report import ReviewIssue, ReviewReport

    report = ReviewReport(
        issues=[
            ReviewIssue(
                file="a.py",
                line=3,
                severity="P1",
                description="possible N+1",
                engine="reasoning",
            )
        ]
    )
    report.build_evidence()
    assert report.issues[0].evidence_envelope.get("confidence") == "derived"
    assert report.issues[0].evidence_envelope.get("status") == "suspected"
    d = report.to_dict()
    assert d["evidence_envelope_summary"]["confirmed_count"] == 0
    assert d["issues"][0]["evidence_envelope"]["status"] == "suspected"


def test_core_facade_validate_and_attach():
    from core.api.core_facade import (
        allow_evidence_release_block,
        attach_evidence_envelopes,
        validate_evidence_envelope,
    )

    v = validate_evidence_envelope(
        {"status": "confirmed", "confidence": "derived", "evidence": []},
        demote=True,
    )
    assert v["envelope"]["status"] == "suspected"
    attached = attach_evidence_envelopes(
        [{"file": "b.py", "line": 1, "description": "x", "engine": "code_gen"}]
    )
    assert attached["summary"]["suspected_count"] >= 1
    block = allow_evidence_release_block(attached["issues"][0]["evidence_envelope"])
    assert block["allow"] is False
