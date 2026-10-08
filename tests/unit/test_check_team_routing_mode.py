"""W5 seed scanner for routing_mode."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/check_team_routing_mode.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("check_team_routing_mode", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_workspace_seeds_clean():
    mod = _load_mod()
    violations, n = mod.check()
    assert n >= 1
    assert violations == []


def test_risky_without_marker_fails(tmp_path: Path):
    mod = _load_mod()
    p = tmp_path / "bad.yaml"
    p.write_text("stages:\n  - routing_mode: llm\n", encoding="utf-8")
    assert mod._scan_file(p)


def test_risky_with_marker_ok(tmp_path: Path):
    mod = _load_mod()
    p = tmp_path / "ok.yaml"
    p.write_text(
        "stages:\n  # routing-ok: grayscale pilot\n  - routing_mode: llm\n",
        encoding="utf-8",
    )
    assert mod._scan_file(p) == []
