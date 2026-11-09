"""Wave 1–4 engineering gates + evidence card + D26 promote check."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(args):
    return subprocess.run(
        [sys.executable, *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def test_wave_ops_all_passes_engineering():
    proc = _run(["scripts/security_wave_ops.py", "--all"])
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["security_certification"] is False


def test_evidence_card_validate_templates():
    for name in (
        "reports/security/evidence/wave3/text-family-live.card.json",
        "reports/security/evidence/wave3/staging-tenant-blackbox.card.json",
    ):
        proc = _run(["scripts/security_evidence_card.py", "--validate", name])
        assert proc.returncode == 0, proc.stdout
        assert json.loads(proc.stdout)["ok"] is True


def test_d26_promote_check_blocks_propose_without_pilot():
    proc = _run(["scripts/security_d26_promote_check.py", "--propose-e"])
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["d26_promote_allowed"] is False
    assert payload["d26_status"] != "E" or payload["yaml_e_without_pilot"] is False


def test_d26_promote_check_ok_when_not_proposing():
    proc = _run(["scripts/security_d26_promote_check.py"])
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
