"""security_publish_gates wrapper modes."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(mode: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/security_publish_gates.py", "--mode", mode],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def test_ledger_mode_passes():
    proc = _run("ledger")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["mode"] == "ledger"
    assert payload["ok"] is True
    assert payload["security_certification"] is False


def test_release_and_claim_honestly_fail_today():
    rel = _run("release")
    claim = _run("claim")
    assert rel.returncode == 1
    assert claim.returncode == 1
    r = json.loads(rel.stdout)
    c = json.loads(claim.stdout)
    assert r["release_ok"] is False
    assert c["coverage_ok"] is False
    assert r["security_certification"] is False
