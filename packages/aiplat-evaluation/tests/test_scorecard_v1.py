"""Scorecard v1 honesty — no silent 5/5 while gaps remain."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD = ROOT / "docs/a3/scorecard_v1.json"
SCRIPT = ROOT / "scripts/scorecard_v1_check.sh"


def test_scorecard_json_schema():
    data = json.loads(CARD.read_text(encoding="utf-8"))
    assert data["schema"] == "eval.scorecard.v1"
    assert data["accuracy_claim"] is False
    assert data["process_split_authorized"] is False
    assert data["axes"]["feature_coverage"]["score"] < 5.0
    assert data["axes"]["feature_coverage"]["score"] >= 4.6
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
    assert dims["compliance_pii_v0"]["evidence_ok"] is True
    assert dims["g2b_prep"]["evidence_ok"] is True
    assert dims["preference_v0"]["evidence_ok"] is False


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
