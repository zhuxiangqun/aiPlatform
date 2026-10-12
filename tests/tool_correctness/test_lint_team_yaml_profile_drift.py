"""Self-test for scripts/lint_team_yaml_profile_drift.py (O2)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "lint_team_yaml_profile_drift.py"

yaml = pytest.importorskip("yaml")


@pytest.fixture(scope="module")
def drift():
    spec = importlib.util.spec_from_file_location("lint_team_yaml_profile_drift", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_detects_profile_drift(drift, tmp_path, monkeypatch):
    agents = tmp_path / "agents" / "coder"
    agents.mkdir(parents=True)
    (agents / "AGENT.md").write_text(
        "---\nagent_type: react\narchitecture_profile: react_tools\n---\nbody\n",
        encoding="utf-8",
    )
    team = tmp_path / "teams" / "demo.yaml"
    team.parent.mkdir(parents=True)
    team.write_text(
        "stages:\n"
        "  - agent_id: coder\n"
        "    architecture_profile: oneshot\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    msgs = drift.lint_team_file(team)
    assert msgs and "architecture_profile" in msgs[0]


def test_drift_ok_comment(drift, tmp_path):
    team = tmp_path / "t.yaml"
    team.write_text("# drift-ok: intentional oneshot override for demo\nstages: []\n", encoding="utf-8")
    assert drift._has_drift_ok(team) is True
