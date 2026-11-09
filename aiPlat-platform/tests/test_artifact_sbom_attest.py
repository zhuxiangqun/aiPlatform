"""P2-1: SBOM + allowlist + attest gate (importlib; no CoreFacade)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SBOM_PATH = ROOT / "builder" / "artifact_sbom_attest.py"
ASM_PATH = ROOT / "builder" / "artifact_security_manifest.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mods():
    sbom = _load("artifact_sbom_attest_under_test", SBOM_PATH)
    # Register under builder.* so asm can import
    sys.modules["builder"] = sys.modules.get("builder") or type(sys)("builder")
    sys.modules["builder.artifact_sbom_attest"] = sbom
    asm = _load("artifact_security_manifest_p21", ASM_PATH)
    sys.modules["builder.artifact_security_manifest"] = asm
    return sbom, asm


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AIPLAT_ARTIFACT_MANIFEST_HMAC_SECRET", "test-secret-p2-1")
    monkeypatch.delenv("AIPLAT_PROFILE", raising=False)
    monkeypatch.delenv("AIPLAT_ENV", raising=False)
    monkeypatch.delenv("AIPLAT_P2_1_SBOM", raising=False)
    monkeypatch.delenv("AIPLAT_ARTIFACT_MANIFEST_ED25519_SEED", raising=False)


def test_generate_sbom_from_requirements(mods, tmp_path: Path):
    sbom, _ = mods
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\nflask>=2.0\n", encoding="utf-8")
    bom = sbom.generate_sbom_cyclonedx_lite(tmp_path, artifact_id="demo@1")
    assert bom["bomFormat"] == "CycloneDX"
    names = {c["name"] for c in bom["components"]}
    assert "requests" in names
    assert "flask" in names
    digest = sbom.sbom_digest(bom)
    assert len(digest) == 64


def test_allowlist_blocks_undeclared_mcp(mods, tmp_path: Path):
    sbom, _ = mods
    (tmp_path / "mcp.json").write_text(
        json.dumps({"mcpServers": {"evil-server": {"command": "npx"}}}),
        encoding="utf-8",
    )
    al = {
        "mcp_servers": ["safe-server"],
        "plugins": [],
        "missing": False,
    }
    out = sbom.evaluate_mcp_plugin_allowlist(tmp_path, allowlist=al)
    assert out["ok"] is False
    assert "evil-server" in out["undeclared_mcp"]


def test_allowlist_pass_when_listed(mods, tmp_path: Path):
    sbom, _ = mods
    (tmp_path / "mcp.json").write_text(
        json.dumps({"mcpServers": {"safe-server": {}}}),
        encoding="utf-8",
    )
    al = {"mcp_servers": ["safe-server"], "plugins": [], "missing": False}
    out = sbom.evaluate_mcp_plugin_allowlist(tmp_path, allowlist=al)
    assert out["ok"] is True


def test_p2_1_gate_requires_sbom_when_enforced(mods):
    sbom, _ = mods
    gate = sbom.evaluate_p2_1_gate(
        sbom_digest_value="",
        component_count=0,
        allowlist={"ok": True},
        require_sbom=True,
    )
    assert gate["ok"] is False
    assert "sbom_missing" in gate["blockers"]
    gate2 = sbom.evaluate_p2_1_gate(
        sbom_digest_value="abc",
        component_count=0,
        allowlist={"ok": True},
        require_sbom=True,
    )
    assert gate2["ok"] is True


def test_build_and_gate_includes_sbom(mods, tmp_path: Path, monkeypatch):
    sbom, asm = mods
    monkeypatch.setenv("AIPLAT_P2_1_SBOM", "1")
    (tmp_path / "requirements.txt").write_text("httpx==0.27.0\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    # Point allowlist to empty-ok path (no mcp declared)
    monkeypatch.setenv(
        "AIPLAT_MCP_PLUGIN_ALLOWLIST",
        str(tmp_path / "allow.json"),
    )
    (tmp_path / "allow.json").write_text(
        json.dumps({"mcp_servers": [], "plugins": []}),
        encoding="utf-8",
    )
    out = asm.build_and_gate_for_dir(
        tmp_path,
        artifact_id="p21-demo",
        artifact_type="app",
        owner="test",
        write=True,
    )
    assert (tmp_path / "sbom.cdx.json").is_file()
    assert out["manifest"]["sbom"]["digest"]
    assert out["manifest"]["security_certification"] is False
    # sast may fail without bandit — gate may block; but p2_1 sbom attached
    assert out["p2_1"]["sbom_digest"]
    # Force scans pass to isolate p2_1
    m = dict(out["manifest"])
    m["sast"] = {"status": "pass", "tool": "none"}
    m["secrets_scan"] = {"status": "pass"}
    m["deps_scan"] = {"status": "pass"}
    # re-sign after mutation
    m["security_certification"] = False
    h = asm.compute_manifest_hash(m)
    m["manifest_hash"] = h
    m["signature"] = asm.sign_manifest_hash(h)
    gate = asm.evaluate_publish_gate(m, require_sbom=True)
    assert gate["ok"] is True
    assert gate["p2_1"]["ok"] is True


def test_http_unsigned_blocked_in_prodish(mods, monkeypatch):
    _, asm = mods
    monkeypatch.setenv("AIPLAT_PROFILE", "production")
    monkeypatch.delenv("AIPLAT_ARTIFACT_MANIFEST_HMAC_SECRET", raising=False)
    m = asm.build_manifest(
        artifact_id="a",
        artifact_type="app",
        owner="t",
        sast={"status": "pass"},
        secrets_scan={"status": "pass"},
        deps_scan={"status": "pass"},
        extra={"sbom": {"digest": "x", "component_count": 1}, "mcp_plugin_allowlist": {"ok": True}},
    )
    assert m["signature"] == "unsigned_dev"
    integ = asm.validate_manifest_integrity(m)
    assert integ["ok"] is False
    assert "unsigned_not_allowed_in_prodish" in integ["errors"]
