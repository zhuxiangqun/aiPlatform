"""Pi thin Runtime export helper (deploy one-click)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_MOD_PATH = _ROOT / "aiPlat-platform" / "builder" / "pi_bundle_export.py"


def _load():
    # Avoid builder/__init__.py → core_facade (needs Python 3.10+ on some hosts)
    name = "aiplat_pi_bundle_export_under_test"
    spec = importlib.util.spec_from_file_location(name, _MOD_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_export_sample_app(tmp_path: Path):
    mod = _load()
    sample = (
        mod.workspace_root()
        / "packages"
        / "aiplat-pi-runtime"
        / "fixtures"
        / "sample-app"
    )
    assert sample.is_dir(), sample
    out = tmp_path / "pi-out"
    r = mod.export_pi_bundle_for_project(
        "sample-test",
        app_home=str(sample),
        out=str(out),
    )
    assert r.get("ok") is True, r
    assert (out / "agent_manifest.json").is_file()
    assert (out / "skills" / "greet" / "SKILL.md").is_file()
    assert (out / "extensions" / "aiplat-app.ts").is_file()
    assert (out / "package.json").is_file()


def test_skip_without_manifest(tmp_path: Path):
    mod = _load()
    empty = tmp_path / "empty"
    empty.mkdir()
    r = mod.try_export_after_deploy("x", str(empty))
    assert r.get("ok") is False
    assert r.get("skipped") is True


def test_zip_pi_bundle(tmp_path: Path, monkeypatch):
    mod = _load()
    sample = (
        mod.workspace_root()
        / "packages"
        / "aiplat-pi-runtime"
        / "fixtures"
        / "sample-app"
    )
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))
    out = tmp_path / "pi-out"
    r = mod.export_pi_bundle_for_project(
        "zip-test",
        app_home=str(sample),
        out=str(out),
    )
    assert r.get("ok") is True, r
    # Reuse exported dir via default_out_dir (zip path prefers existing package)
    monkeypatch.setattr(mod, "default_out_dir", lambda _pid: out)
    zip_path, meta = mod.zip_pi_bundle_for_project("zip-test")
    assert zip_path is not None and zip_path.is_file(), meta
    assert zip_path.suffix == ".zip"
    assert meta.get("ok") is True
    # Also zip with explicit app_home when no prior export under AIPLAT_HOME
    zip2, meta2 = mod.zip_pi_bundle_for_project(
        "zip-test-2", app_home=str(sample)
    )
    assert zip2 is not None and zip2.is_file(), meta2
