"""Phase 4: security preflight summarize + evolve_proposal gate."""

from __future__ import annotations

from core.apps.fde.service.evolve_proposal_gate import (
    enqueue_evolve_proposal,
    evaluate_evolve_proposal,
)
from core.apps.fde.service.security_preflight import (
    get_latest_preflight,
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
