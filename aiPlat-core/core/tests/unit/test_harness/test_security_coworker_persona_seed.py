"""Security coworker persona seed — OpenWorker-inspired packaging."""
from __future__ import annotations

from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[4]  # aiPlat-core/
_SEEDS = _ROOT / "core" / "workspace_seeds"


def _agents_dir() -> Path:
    return _SEEDS / "agents"


def test_security_coworker_agent_frontmatter():
    path = _agents_dir() / "security_coworker" / "AGENT.md"
    assert path.is_file(), path
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---")
    parts = text.split("---", 2)
    meta = yaml.safe_load(parts[1])
    assert meta["name"] == "security_coworker"
    assert "security_plan" in meta["required_skills"]
    assert "security_report" in meta["required_skills"]
    assert "model" not in meta  # §12 — no hardcoded model
    assert "model" not in (meta.get("config") or {})
    # Handoff 5 fields present in body
    body = parts[2] if len(parts) > 2 else ""
    for key in ("做了什么", "产出物在哪", "如何验证", "已知问题", "下一步"):
        assert key in body


def test_security_stage_agents_seeded():
    for aid in (
        "security_planner",
        "security_tracer",
        "security_critic",
        "security_reporter",
        "security_evidencer",
    ):
        p = _agents_dir() / aid / "AGENT.md"
        assert p.is_file(), p
        meta = yaml.safe_load(p.read_text(encoding="utf-8").split("---", 2)[1])
        assert meta["name"] == aid
        assert "model" not in meta


def test_persona_manifest_points_to_team():
    path = _SEEDS / "personas" / "security_coworker" / "PERSONA.md"
    assert path.is_file()
    meta = yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])
    assert meta["id"] == "security_coworker"
    assert meta["recommended_team"] == "security_review"
    assert meta["recommended_attendance"] == "inbox"


def test_security_review_team_still_loads():
    from core.harness.execution.team_planner import load_team_template

    tpl = load_team_template("security_review")
    assert tpl is not None
    assert tpl.name == "security_review"
    ids = [s.get("id") for s in tpl.stages]
    assert "security_plan" in ids
    assert "security_report" in ids


def test_server_persona_seed_block_present():
    """Wiring: startup materializes personas like agents (do-not-overwrite)."""
    server_py = _ROOT / "core" / "server.py"
    text = server_py.read_text(encoding="utf-8")
    assert 'workspace_seeds" / "personas"' in text or "workspace_seeds' / 'personas'" in text
    assert ".aiplat" in text and "personas" in text
