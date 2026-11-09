"""P0-3a: artifact.security.json hash/sign/gate regressions (no CoreFacade import)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "builder" / "artifact_security_manifest.py"


def _load():
    name = "artifact_security_manifest_under_test"
    spec = importlib.util.spec_from_file_location(name, MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def asm():
    return _load()


@pytest.fixture(autouse=True)
def _hmac(monkeypatch):
    monkeypatch.setenv("AIPLAT_ARTIFACT_MANIFEST_HMAC_SECRET", "test-secret-p0-3a")
    monkeypatch.delenv("AIPLAT_PROFILE", raising=False)
    monkeypatch.delenv("AIPLAT_ENV", raising=False)


def test_canonical_hash_stable_and_excludes_signature(asm):
    m1 = asm.build_manifest(
        artifact_id="a@1",
        artifact_type="app",
        owner="t",
        sast={"status": "pass", "tool": "none"},
        secrets_scan={"status": "pass"},
        deps_scan={"status": "pass"},
    )
    h1 = m1["manifest_hash"]
    assert h1 == asm.compute_manifest_hash(m1)
    m1_tampered = dict(m1)
    m1_tampered["sast"] = {"status": "pass", "tool": "hacked"}
    assert asm.validate_manifest_integrity(m1_tampered)["ok"] is False
    assert "manifest_hash_mismatch" in asm.validate_manifest_integrity(m1_tampered)["errors"]


def test_hand_edit_pass_invalidates_signature(asm, tmp_path: Path):
    m = asm.build_manifest(
        artifact_id="a@1",
        artifact_type="app",
        owner="t",
        sast={"status": "pass", "tool": "none"},
        secrets_scan={"status": "pass"},
        deps_scan={"status": "pass"},
    )
    path = asm.write_manifest(tmp_path / asm.MANIFEST_NAME, m)
    raw = json.loads(path.read_text())
    raw["secrets_scan"]["status"] = "fail"
    assert asm.validate_manifest_integrity(raw)["ok"] is False


def test_publish_gate_blocks_fail_scans(asm):
    m = asm.build_manifest(
        artifact_id="a@1",
        artifact_type="app",
        owner="t",
        sast={"status": "fail", "tool": "unset"},
        secrets_scan={"status": "pass"},
        deps_scan={"status": "pass"},
    )
    gate = asm.evaluate_publish_gate(m)
    assert gate["ok"] is False
    assert any("sast_not_pass" in b for b in gate["blockers"])


def test_unsigned_blocked_in_production(asm, monkeypatch):
    monkeypatch.delenv("AIPLAT_ARTIFACT_MANIFEST_HMAC_SECRET", raising=False)
    monkeypatch.setenv("AIPLAT_PROFILE", "production")
    m = asm.build_manifest(
        artifact_id="a@1",
        artifact_type="app",
        owner="t",
        sast={"status": "pass", "tool": "none"},
        secrets_scan={"status": "pass"},
        deps_scan={"status": "pass"},
    )
    assert m["signature"] == "unsigned_dev"
    gate = asm.evaluate_publish_gate(m)
    assert gate["ok"] is False
    assert any("unsigned" in b for b in gate["blockers"])


def test_secrets_scan_finds_key(asm, tmp_path: Path):
    (tmp_path / "app.py").write_text('KEY = "sk-abcdefghijklmnopqrstuvwxyz"\n', encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("flask==3.0.0\n", encoding="utf-8")
    r = asm.scan_secrets_in_tree(tmp_path)
    assert r["status"] == "fail"
    assert r["hits"]


def test_build_and_gate_clean_tree(asm, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_ARTIFACT_MANIFEST_HMAC_SECRET", "test-secret-p0-3a")
    (tmp_path / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("flask==3.0.0\n", encoding="utf-8")
    monkeypatch.setattr(
        asm,
        "scan_sast_stub",
        lambda root: {"status": "pass", "tool": "test-stub"},
    )
    out = asm.build_and_gate_for_dir(
        tmp_path,
        artifact_id="proj-1",
        artifact_type="app",
        owner="qa",
        write=True,
    )
    assert out["publish_allowed"] is True
    assert (tmp_path / asm.MANIFEST_NAME).is_file()
