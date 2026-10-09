"""Same-profile gold gate — ReviewBench model/prompt change discipline."""

from __future__ import annotations

import time

from core.harness.evaluation.agent_config_diff import compute_agent_diff
from core.harness.evaluation.gold_profile_gate import (
    attach_gold_gate_to_diff,
    evaluate_gold_profile_gate,
)


def _clear(monkeypatch):
    monkeypatch.delenv("AIPLAT_GOLD_PROFILE_GATE", raising=False)
    monkeypatch.delenv("AIPLAT_GOLD_GATE_MAX_AGE_HOURS", raising=False)
    monkeypatch.delenv("AIPLAT_GOLD_GATE_MAX_P0_MISS", raising=False)
    monkeypatch.delenv("AIPLAT_GOLD_GATE_PROFILE", raising=False)


def test_skip_on_low_risk(monkeypatch):
    _clear(monkeypatch)
    out = evaluate_gold_profile_gate(risk_level="low", reports=[])
    assert out["verdict"] == "skip"
    assert out["ok"] is True


def test_require_eval_when_no_reports(monkeypatch):
    _clear(monkeypatch)
    out = evaluate_gold_profile_gate(risk_level="high", reports=[], profile="balanced")
    assert out["verdict"] == "require_eval"
    assert out["ok"] is False


def test_pass_fresh_same_profile(monkeypatch):
    _clear(monkeypatch)
    now = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    reports = [
        {
            "profile": "balanced",
            "precision": 0.9,
            "recall": 0.8,
            "p0_recall": 1.0,
            "novel_count": 0,
            "written_at": now,
        },
    ]
    out = evaluate_gold_profile_gate(risk_level="high", reports=reports, profile="balanced")
    assert out["verdict"] == "pass"
    assert out["ok"] is True


def test_block_on_regression(monkeypatch):
    _clear(monkeypatch)
    now = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    reports = [
        {"profile": "balanced", "precision": 0.9, "recall": 0.8, "p0_recall": 1.0, "written_at": "20260101T000000Z"},
        {"profile": "balanced", "precision": 0.7, "recall": 0.6, "p0_recall": 0.5, "written_at": now},
    ]
    out = evaluate_gold_profile_gate(risk_level="high", reports=reports, profile="balanced")
    assert out["verdict"] == "block_regression"
    assert out["ok"] is False


def test_wrong_profile_counts_as_missing(monkeypatch):
    _clear(monkeypatch)
    now = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    reports = [
        {"profile": "high_coverage", "precision": 0.9, "recall": 0.9, "p0_recall": 1.0, "written_at": now},
    ]
    out = evaluate_gold_profile_gate(risk_level="high", reports=reports, profile="low_noise")
    assert out["verdict"] == "require_eval"


def test_stale_requires_eval(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AIPLAT_GOLD_GATE_MAX_AGE_HOURS", "1")
    reports = [
        {
            "profile": "balanced",
            "precision": 0.9,
            "recall": 0.8,
            "p0_recall": 1.0,
            "written_at": "20200101T000000Z",
        },
    ]
    out = evaluate_gold_profile_gate(risk_level="high", reports=reports)
    assert out["verdict"] == "require_eval"


def test_attach_to_model_diff(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AIPLAT_GOLD_PROFILE_GATE", "on")
    old = "---\nmodel: a\n---\nbody"
    new = "---\nmodel: b\n---\nbody"
    out = compute_agent_diff(old, new)
    assert out["risk_level"] == "high"
    assert "gold_gate" in out
    assert out["gold_gate"]["verdict"] in ("require_eval", "pass", "block_regression")


def test_attach_helper():
    d = attach_gold_gate_to_diff({"risk_level": "low", "summary": "x"}, profile="balanced")
    assert d["gold_gate"]["verdict"] == "skip"
