"""Scorecard v1 honesty — evidence manifest + no silent feature 5."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD = ROOT / "docs/a3/scorecard_v1.json"
MANIFEST = ROOT / "docs/a3/evidence/evidence_manifest.v1.json"
SCRIPT = ROOT / "scripts/scorecard_v1_check.sh"


def test_scorecard_json_schema():
    data = json.loads(CARD.read_text(encoding="utf-8"))
    assert data["schema"] == "eval.scorecard.v1"
    assert data["accuracy_claim"] is False
    assert data["process_split_authorized"] is False
    assert data.get("evidence_manifest")
    feat = data["axes"]["feature_coverage"]
    # Until dual-human attestation is confirmed, feature must stay <5.
    assert feat["score"] < 5.0
    assert feat["full_score_eligible"] is False
    assert "dual_human_attestation_unconfirmed" in (feat.get("gaps") or [])
    assert feat.get("evidence_audit_ok") is False
    arch = data["axes"]["engineering_architecture"]
    assert arch["score"] == 5.0
    assert arch["full_score_eligible"] is True
    assert arch["gaps"] == []
    local = data["axes"]["local_independence_no_microvm"]
    assert local["score"] == 5.0
    assert local["full_score_eligible"] is True
    assert local["gaps"] == []
    assert data["axes"]["local_independence_with_microvm"]["eligible_on_darwin"] is False
    dims = {d["id"]: d for d in data["dimensions"]}
    assert all(d.get("evidence_ok") is True for d in data["dimensions"])
    assert dims["preference_v0"]["evidence_ok"] is True
    assert dims["g2b_prep"]["evidence_ok"] is True


def test_evidence_manifest_hashes():
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert man["schema"] == "eval.scorecard.evidence_manifest.v1"
    assert man["dual_human_attestation"]["status"] == "unconfirmed"
    for ent in man["tracked_aggregates"]:
        path = ROOT / ent["path"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == ent["sha256"], ent["path"]


def test_scorecard_v1_check_script():
    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "PASS" in proc.stdout
    assert "feature_5_allowed" in proc.stdout
