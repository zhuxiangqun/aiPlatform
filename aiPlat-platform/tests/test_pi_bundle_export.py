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
