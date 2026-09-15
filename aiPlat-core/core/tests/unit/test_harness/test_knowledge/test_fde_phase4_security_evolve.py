"""Phase 4 / AI FDE half-step: preflight + evolve gate + apply/rollback + D6 metrics."""

from __future__ import annotations

import pytest

from core.apps.fde.service.evolve_proposal_gate import (
    apply_evolve_proposal,
    approve_evolve_proposal,
    enqueue_evolve_proposal,
    evaluate_evolve_proposal,
    get_evolve_applied_config,
    get_evolve_metrics,
    reject_evolve_proposal,
    rollback_evolve_proposal,
)
from core.apps.fde.service.security_preflight import (
    get_latest_preflight,
    preflight_signoff_gate,
    save_preflight_run,
    summarize_security_dry_run,
)


def test_summarize_preserves_severity():
    dry = {
        "status": "ok",
        "phase": "B",
        "security_report": {
            "findings": [
                {"id": "f1", "title": "x", "severity": "high", "status": "candidate"},
            ]
        },
        "security_evidence": {"enabled": False},
    }
    s = summarize_security_dry_run(dry)
    assert s["phase"] == "B"
    assert s["finding_count"] == 1
    assert s["findings"][0]["severity"] == "high"


def test_save_preflight_latest(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    rec = save_preflight_run(
        dry_run={"status": "ok", "phase": "B", "security_report": {"findings": []}},
        actor="t",
        phase_c_enabled=False,
    )
    assert rec["label"].startswith("FDE 4A")
    assert rec["phase_c_enabled"] is False
    latest = get_latest_preflight()
    assert latest is not None
    assert latest["run_id"] == rec["run_id"]
    assert latest["summary"]["phase"] == "B"


def test_preflight_signoff_gate_blocks_missing_and_high(monkeypatch, tmp_path):
    """Acceptance signoff requires ⑥b; high/critical findings block."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))

    missing = preflight_signoff_gate()
    assert missing["ok"] is False
    assert missing["reason"] == "security_preflight_required"

    save_preflight_run(
        dry_run={
            "status": "ok",
            "phase": "B",
            "security_report": {
                "findings": [{"id": "f1", "title": "x", "severity": "high"}],
            },
        },
        actor="t",
    )
    blocked = preflight_signoff_gate()
    assert blocked["ok"] is False
    assert blocked["reason"] == "high_or_critical_findings"
    assert blocked["blocking_count"] == 1

    save_preflight_run(
        dry_run={
            "status": "ok",
            "phase": "B",
            "security_report": {
                "findings": [{"id": "f2", "title": "y", "severity": "low"}],
            },
        },
        actor="t",
    )
    passed = preflight_signoff_gate()
    assert passed["ok"] is True
    assert passed["status"] == "pass"


def test_evolve_whitelist_allow(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "h"))
    (tmp_path / "h").mkdir()
    g = evaluate_evolve_proposal(keys=["model_config.temperature"])
    assert g["gate_id"] == "evolve_proposal"
    assert g["status"] in {"auto_allow", "admitted_to_hitl"}
    assert "No silent" in g["note"]


def test_evolve_forbidden_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "h"))
    (tmp_path / "h").mkdir()
    g = evaluate_evolve_proposal(keys=["auth.root_password"])
    assert g["status"] == "rejected"
    assert g["passed"] is False


def test_evolve_abox_requires_hitl(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "h"))
    (tmp_path / "h").mkdir()
    g = evaluate_evolve_proposal(
        keys=["model_config.temperature"],
        touches_abox=True,
    )
    assert g["require_hitl"] is True
    assert "abox_or_ontology_write_requires_hitl" in g["reasons"]
    q = enqueue_evolve_proposal(
        keys=["model_config.temperature"],
        touches_abox=True,
        summary="test abox",
    )
    assert q["queued"] is True
    assert q["review_status"] == "pending_hitl"


def test_evolve_apply_rollback_metrics(monkeypatch, tmp_path):
    """AI FDE half-step: approve → apply whitelist config → rollback; D6 metrics."""
    home = tmp_path / "h"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))

    q = enqueue_evolve_proposal(
        keys=["model_config.temperature"],
        proposed_changes={"model_config.temperature": 0.42},
        summary="set temp",
        actor="agent",
    )
    assert q["queued"] is True
    pid = q["proposal_id"]
    assert pid

    if q["review_status"] == "pending_hitl":
        approve_evolve_proposal(pid, actor="fda")
    elif q["review_status"] != "auto_recorded":
        pytest.fail(f"unexpected status {q['review_status']}")

    applied = apply_evolve_proposal(pid, actor="fda")
    assert applied["review_status"] == "observing"
    assert applied.get("observation_until")
    assert get_evolve_applied_config().get("model_config.temperature") == 0.42

    rolled = rollback_evolve_proposal(pid, actor="fda")
    assert rolled["review_status"] == "rolled_back"
    assert "model_config.temperature" not in get_evolve_applied_config()

    m = get_evolve_metrics()
    assert m["applied"] >= 1
    assert m["rolled_back"] >= 1
    assert m["rollback_rate"] > 0
    assert "pass_rate_reference_only" in m
    assert "reference only" in m["note"].lower() or "D6" in m["note"]


def test_evolve_observation_window_and_quality_breach(monkeypatch, tmp_path):
    """Apply → observing → tick to stable; quality drop auto-rollbacks."""
    from core.apps.fde.service.evolve_proposal_gate import (
        list_evolve_applied,
        record_evolve_observation,
        tick_evolve_observations,
    )

    home = tmp_path / "h"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    monkeypatch.setenv("AIPLAT_EVOLVE_OBSERVATION_HOURS", "0.0001")  # ~0.36s
    monkeypatch.setenv("AIPLAT_EVOLVE_QUALITY_DROP_THRESHOLD", "5")

    q = enqueue_evolve_proposal(
        keys=["model_config.temperature"],
        proposed_changes={"model_config.temperature": 0.5},
        summary="obs",
    )
    pid = q["proposal_id"]
    if q["review_status"] == "pending_hitl":
        approve_evolve_proposal(pid)
    applied = apply_evolve_proposal(pid)
    assert applied["review_status"] == "observing"
    assert list_evolve_applied()

    # quality breach → auto rollback
    q2 = enqueue_evolve_proposal(
        keys=["cache_ttl_seconds"],
        proposed_changes={"cache_ttl_seconds": 30},
        summary="breach",
    )
    pid2 = q2["proposal_id"]
    if q2["review_status"] == "pending_hitl":
        approve_evolve_proposal(pid2)
    apply_evolve_proposal(pid2)
    out = record_evolve_observation(
        pid2,
        metric_name="quality_score",
        metric_value=70.0,
        baseline_value=90.0,
        actor="sys",
    )
    assert out.get("review_status") == "rolled_back"
    assert out.get("rollback_reason") == "quality_score_breach"

    # first proposal: wait then tick → stable
    import time as _t

    _t.sleep(0.5)
    tick = tick_evolve_observations()
    assert pid in (tick.get("promoted_stable") or [])
    from core.apps.fde.service.evolve_proposal_gate import get_evolve_proposal

    assert get_evolve_proposal(pid)["review_status"] == "stable"

def test_evolve_reject_increments_hitl_reject(monkeypatch, tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    q = enqueue_evolve_proposal(
        keys=["cache_ttl_seconds"],
        proposed_changes={"cache_ttl_seconds": 60},
        summary="ttl",
    )
    pid = q["proposal_id"]
    # Force pending path: reject from pending or auto_recorded
    if q["review_status"] == "auto_recorded":
        # Still rejectable before apply
        pass
    reject_evolve_proposal(pid, actor="fda", reason="not now")
    m = get_evolve_metrics()
    assert m["rejected_hitl"] >= 1


def test_evolve_abox_cannot_apply(monkeypatch, tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    q = enqueue_evolve_proposal(
        keys=["model_config.temperature"],
        proposed_changes={"model_config.temperature": 0.1},
        touches_abox=True,
        summary="abox",
    )
    pid = q["proposal_id"]
    approve_evolve_proposal(pid, actor="fda")
    with pytest.raises(ValueError, match="abox"):
        apply_evolve_proposal(pid, actor="fda")
