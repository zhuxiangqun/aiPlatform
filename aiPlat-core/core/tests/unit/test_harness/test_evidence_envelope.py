"""Evidence Envelope — no fake confirmed without measured evidence."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.harness.meta.evidence_envelope import (
    allow_release_block,
    attach_envelopes_to_issues,
    envelope_for_gold_block,
    envelope_from_review_issue,
    evidence_item,
    gate_duty_status_with_envelopes,
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
    """Facade thin wrappers — skip if host Python cannot import core_facade (e.g. 3.9 |)."""
    facade_path = (
        Path(__file__).resolve().parents[3] / "api" / "core_facade.py"
    )
    text = facade_path.read_text(encoding="utf-8")
    assert "def validate_evidence_envelope" in text
    assert "def attach_evidence_envelopes" in text
    assert "def allow_evidence_release_block" in text

    try:
        from core.api.core_facade import (
            allow_evidence_release_block,
            attach_evidence_envelopes,
            validate_evidence_envelope,
        )
    except TypeError as exc:
        pytest.skip(f"core_facade import needs Python 3.10+ ({exc})")

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


def test_envelope_for_gold_block_allows_release_block():
    env = envelope_for_gold_block(
        reason="gold_regressing",
        p0_miss_rate=0.3,
        regressing=True,
        written_at="2026-10-10T12:00:00Z",
    )
    ok, why = allow_release_block(env)
    assert ok is True
    assert why == "blocked_measured"
    assert env["status"] == "blocked"
    assert env["confidence"] == "measured"
    assert env["evidence"]
    assert env["limitations"]


def test_gate_duty_status_demotes_block_without_allow():
    st, extras, rows = gate_duty_status_with_envelopes(
        "block",
        [
            {
                "status": "suspected",
                "confidence": "derived",
                "evidence": [evidence_item(type="file_line", ref="a.py:1")],
                "limitations": ["static only"],
                "next_check": "measure",
            }
        ],
    )
    assert st == "watch"
    assert "block_demoted_no_envelope_allow_release_block" in extras
    assert rows and rows[0]["allow_block"] is False

    st2, extras2, rows2 = gate_duty_status_with_envelopes(
        "block",
        [envelope_for_gold_block(reason="p0_miss_rate=0.5>0.2", p0_miss_rate=0.5)],
    )
    assert st2 == "block"
    assert not extras2
    assert rows2[0]["allow_block"] is True
