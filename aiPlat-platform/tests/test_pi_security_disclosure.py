"""P0-4: Pi exporter auto security disclosure."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _hmac(monkeypatch):
    monkeypatch.setenv("AIPLAT_ARTIFACT_MANIFEST_HMAC_SECRET", "test-secret-p0-4")
    monkeypatch.delenv("AIPLAT_PROFILE", raising=False)


def test_write_pi_security_disclosure_auto(tmp_path: Path, monkeypatch):
    # Load disclosure helper without importing builder package __init__
    asm = _load("asm_p04", ROOT / "builder" / "artifact_security_manifest.py")
    # Inject as builder.artifact_security_manifest for pi_bundle_export import
    import types

    pkg = types.ModuleType("builder")
    pkg.artifact_security_manifest = asm
    sys.modules["builder"] = pkg
    sys.modules["builder.artifact_security_manifest"] = asm

    pi = _load("pi_export_p04", ROOT / "builder" / "pi_bundle_export.py")
    out = pi.write_pi_security_disclosure(tmp_path / "bundle", project_id="p1")
    assert out["ok"] is True
    disc = json.loads(Path(out["disclosure_path"]).read_text())
    assert "PolicyGate" in disc["platform_controls_lost_on_export"]
    assert disc["security_certification"] is False
    assert "平台级安全" in disc["claim_boundary"]
    man = json.loads(Path(out["manifest_path"]).read_text())
    assert man["type"] == "pi"
    assert man["platform_controls_lost_on_export"]
