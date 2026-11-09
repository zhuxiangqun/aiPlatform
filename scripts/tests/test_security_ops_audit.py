"""Ops audit script — report-only, never claims certification."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "scripts" / "security_ops_audit.py"


def _load():
    spec = importlib.util.spec_from_file_location("security_ops_audit_ut", MOD)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def audit():
    return _load()


def test_hard_floor_ok_when_enabled(audit, monkeypatch):
    monkeypatch.delenv("AIPLAT_HARD_FLOOR_DISABLED", raising=False)
    monkeypatch.delenv("AIPLAT_HARD_FLOOR_DISABLED_UNTIL", raising=False)
    out = audit.check_hard_floor()
    assert out["ok"] is True
    assert out["security_certification"] is False


def test_hard_floor_fails_without_until(audit, monkeypatch):
    monkeypatch.setenv("AIPLAT_HARD_FLOOR_DISABLED", "1")
    monkeypatch.delenv("AIPLAT_HARD_FLOOR_DISABLED_UNTIL", raising=False)
    out = audit.check_hard_floor()
    assert out["ok"] is False
    assert "hard_floor_disabled_without_valid_until" in out["issues"]


def test_p2_1_allowlist_present(audit, monkeypatch):
    monkeypatch.delenv("AIPLAT_PROFILE", raising=False)
    monkeypatch.delenv("AIPLAT_ENV", raising=False)
    monkeypatch.delenv("AIPLAT_ARTIFACT_MANIFEST_HMAC_SECRET", raising=False)
    out = audit.check_p2_1_keys()
    assert out["allowlist_present"] is True
    # Non-prodish: missing secrets are OK
    assert out["ok"] is True
    assert out["security_certification"] is False


def test_run_ops_audit_schema(audit, monkeypatch):
    monkeypatch.delenv("AIPLAT_PROFILE", raising=False)
    monkeypatch.delenv("AIPLAT_ENV", raising=False)
    report = audit.run_ops_audit()
    assert report["schema"] == "eval.security_ops_audit.v1"
    assert report["security_certification"] is False
    assert report["accuracy_claim"] is False
    assert "ir_contacts" in report["checks"]
    assert "engineering_closeout" in report["checks"]
    # Contacts typically missing in CI/dev → ok may be False; still exit-0 path
    assert isinstance(report["failing_checks"], list)


def test_main_exit_zero_without_strict(audit, monkeypatch, capsys):
    monkeypatch.setattr(audit.sys, "argv", ["security_ops_audit.py"])
    # Ensure contacts missing so report may be not-ok
    monkeypatch.delenv("AIPLAT_IR_CONTACTS_PATH", raising=False)
    code = audit.main()
    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["security_certification"] is False


def test_main_strict_fails_when_contacts_missing(audit, monkeypatch, tmp_path, capsys):
    # Explicit AIPLAT_IR_CONTACTS_PATH is exclusive — no fallthrough to contacts.local.yaml
    monkeypatch.setenv("AIPLAT_IR_CONTACTS_PATH", str(tmp_path / "nope.yaml"))
    monkeypatch.setattr(audit.sys, "argv", ["security_ops_audit.py", "--strict"])
    code = audit.main()
    assert code == 1
    err = capsys.readouterr().err
    assert "FAIL --strict" in err
