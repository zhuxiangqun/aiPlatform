"""P0-3b authz pilot CLI — dry-run / status only (no live HTTP)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "scripts" / "security_authz_pilot_cli.py"


def _load():
    spec = importlib.util.spec_from_file_location("security_authz_pilot_cli_ut", MOD)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_dry_run_exit_passes():
    cli = _load()
    code = cli.main(["--dry-run-exit"])
    assert code == 0


def test_status_exit_zero(tmp_path, capsys, monkeypatch):
    cli = _load()
    ledger = tmp_path / "authz_pilot.json"
    monkeypatch.setenv("AIPLAT_AUTHZ_PILOT_PATH", str(ledger))
    code = cli.main(["--status", "--path", str(ledger)])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["security_certification"] is False
    assert out["evaluation"]["status"] == "in_progress"


def test_probe_requires_args():
    cli = _load()
    assert cli.main(["--probe"]) == 2
