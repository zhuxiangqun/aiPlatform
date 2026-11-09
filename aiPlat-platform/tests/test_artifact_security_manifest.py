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
    monkeypatch.delenv("AIPLAT_REQUIRE_THREAT_MODEL", raising=False)
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
    assert out["manifest"]["threat_model"]["status"] == "na"
    assert (tmp_path / asm.MANIFEST_NAME).is_file()


def _valid_tm_doc(**overrides):
    doc = {
        "version": "1.0",
        "asset": "demo-app",
        "actors": ["user", "attacker"],
        "trust_boundaries": ["api"],
        "top_threats": ["idor"],
        "mitigations": ["authz"],
        "out_of_scope": ["physical"],
        "data_classes": ["pii"],
        "auth_assumptions": ["jwt"],
        "tools": ["http"],
        "egress": ["none"],
        "privacy": ["mask"],
        "data_sensitivity": ["medium"],
        "severity": ["high"],
        "likelihood": ["medium"],
        "residual_risk": ["low"],
        "owner": "builder",
        "reviewed_at": "2026-11-09",
        "reviewed_by": "sec-owner",
        "reviewer_role": "security_owner",
        "approved": True,
    }
    doc.update(overrides)
    return doc


def test_threat_model_empty_top_threats_fail(asm):
    r = asm.validate_threat_model_doc(_valid_tm_doc(top_threats=[]))
    assert r["ok"] is False
    assert "empty_top_threats" in r["errors"]


def test_threat_model_self_approval_fail(asm):
    r = asm.validate_threat_model_doc(
        _valid_tm_doc(owner="alice", reviewed_by="Alice", approved=True)
    )
    assert r["ok"] is False
    assert "self_approval_forbidden" in r["errors"]


def test_threat_model_approved_false_fail(asm):
    r = asm.validate_threat_model_doc(_valid_tm_doc(approved=False))
    assert r["status"] == "fail"
    assert "not_approved" in r["errors"]


def test_threat_model_hash_mismatch_blocks_gate(asm):
    tm = {
        "status": "pass",
        "evidence": "ok",
        "hash": "abc",
        "approved": True,
    }
    m = asm.build_manifest(
        artifact_id="a@1",
        artifact_type="app",
        owner="t",
        sast={"status": "pass", "tool": "none"},
        secrets_scan={"status": "pass"},
        deps_scan={"status": "pass"},
        threat_model=tm,
    )
    # Tamper top-level hash after sign → integrity + threat hash checks
    m["threat_model_hash"] = "deadbeef"
    # Recompute would fail integrity; also force status pass path
    gate = asm.evaluate_publish_gate(m)
    assert gate["ok"] is False


def test_na_not_pass_when_required(asm):
    m = asm.build_manifest(
        artifact_id="a@1",
        artifact_type="app",
        owner="t",
        sast={"status": "pass", "tool": "none"},
        secrets_scan={"status": "pass"},
        deps_scan={"status": "pass"},
    )
    assert m["threat_model"]["status"] == "na"
    gate = asm.evaluate_publish_gate(m, require_threat_model=True)
    assert gate["ok"] is False
    assert any("threat_model_required:na" in b for b in gate["blockers"])


def test_cert_true_forbidden(asm):
    m = asm.build_manifest(
        artifact_id="a@1",
        artifact_type="app",
        owner="t",
        sast={"status": "pass", "tool": "none"},
        secrets_scan={"status": "pass"},
        deps_scan={"status": "pass"},
    )
    m["security_certification"] = True
    # integrity will also fail because cert flipped after hash — either way blocked
    gate = asm.evaluate_publish_gate(m)
    assert gate["ok"] is False


def test_threat_model_symlink_escape_fail(asm, tmp_path: Path):
    outside = tmp_path / "outside.yaml"
    outside.write_text("asset: x\n", encoding="utf-8")
    root = tmp_path / "art"
    root.mkdir()
    link = root / "THREAT_MODEL.yaml"
    link.symlink_to(outside)
    tm = asm.load_or_stub_threat_model(root)
    assert tm["status"] == "fail"
    assert "path_escape" in tm["evidence"]


def test_valid_threat_model_file_pass(asm, tmp_path: Path):
    import yaml

    doc = _valid_tm_doc()
    (tmp_path / "THREAT_MODEL.yaml").write_text(
        yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8"
    )
    tm = asm.load_or_stub_threat_model(tmp_path)
    assert tm["status"] == "pass"
    assert tm["hash"]
    m = asm.build_manifest(
        artifact_id="a@1",
        artifact_type="app",
        owner="t",
        sast={"status": "pass", "tool": "none"},
        secrets_scan={"status": "pass"},
        deps_scan={"status": "pass"},
        threat_model=tm,
    )
    gate = asm.evaluate_publish_gate(m, require_threat_model=True)
    assert gate["ok"] is True, gate["blockers"]


def test_crud_pilot_type_requires_threat_model(asm, monkeypatch):
    monkeypatch.delenv("AIPLAT_REQUIRE_THREAT_MODEL", raising=False)
    monkeypatch.delenv("AIPLAT_PROFILE", raising=False)
    m = asm.build_manifest(
        artifact_id="a@1",
        artifact_type="app",
        owner="t",
        sast={"status": "pass", "tool": "none"},
        secrets_scan={"status": "pass"},
        deps_scan={"status": "pass"},
        extra={"app_type": "crud"},
    )
    assert m["threat_model"]["status"] == "na"
    gate = asm.evaluate_publish_gate(m)
    assert gate["ok"] is False
    assert any("threat_model_required:na" in b for b in gate["blockers"])


def test_na_expired_blocks(asm, monkeypatch):
    monkeypatch.delenv("AIPLAT_REQUIRE_THREAT_MODEL", raising=False)
    monkeypatch.delenv("AIPLAT_PROFILE", raising=False)
    tm = {
        "status": "na",
        "evidence": "deferred",
        "hash": "",
        "na_reason": "legacy",
        "expires_at": "2020-01-01T00:00:00Z",
    }
    m = asm.build_manifest(
        artifact_id="a@1",
        artifact_type="app",
        owner="t",
        sast={"status": "pass", "tool": "none"},
        secrets_scan={"status": "pass"},
        deps_scan={"status": "pass"},
        threat_model=tm,
        extra={"app_type": "unknown"},
    )
    gate = asm.evaluate_publish_gate(m, require_threat_model=False)
    assert gate["ok"] is False
    assert any("threat_model_na_expired" in b for b in gate["blockers"])


def test_env_off_ignored_in_production(asm, monkeypatch):
    monkeypatch.setenv("AIPLAT_REQUIRE_THREAT_MODEL", "0")
    monkeypatch.setenv("AIPLAT_PROFILE", "production")
    assert asm.threat_model_required(app_type="unknown") is True
    monkeypatch.setenv("AIPLAT_PROFILE", "development")
    assert asm.threat_model_required(app_type="unknown") is False
