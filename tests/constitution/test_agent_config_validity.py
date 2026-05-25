"""
Constitution test: AGENT.md configuration validity.

Enforces that all AGENT.md files (engine + workspace) are well-formed,
have required fields, and use compatible model names.
"""

import os
import sys
from pathlib import Path

# Ensure aiPlat-core is importable
_CORE_DIR = Path(__file__).resolve().parents[2] / "aiPlat-core"
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def agent_validator():
    from core.management.agent_config_validator import validate_agent_file
    return validate_agent_file


class TestAgentConfigValidity:
    """All AGENT.md files must pass YAML + schema + model validation."""

    def test_engine_agents_yaml_valid(self, agent_validator):
        """Engine agents: YAML frontmatter must parse without errors."""
        engine_dir = WORKSPACE_ROOT / "aiPlat-core" / "core" / "engine" / "agents"
        if not engine_dir.exists():
            pytest.skip("No engine agents directory")
        all_issues = []
        for md_path in sorted(engine_dir.rglob("AGENT.md")):
            if "__pycache__" in str(md_path):
                continue
            for issue in agent_validator(md_path):
                if issue.severity == "error":
                    all_issues.append(f"{md_path.parent.name}: {issue.message}")
        assert not all_issues, (
            f"Engine agent YAML parse errors:\n  " + "\n  ".join(all_issues)
        )

    def test_engine_agents_have_model(self, agent_validator):
        """Engine agents: must have model field configured."""
        engine_dir = WORKSPACE_ROOT / "aiPlat-core" / "core" / "engine" / "agents"
        if not engine_dir.exists():
            pytest.skip("No engine agents directory")
        missing = []
        for md_path in sorted(engine_dir.rglob("AGENT.md")):
            if "__pycache__" in str(md_path):
                continue
            raw = md_path.read_text(encoding="utf-8", errors="replace")
            if "model:" not in raw:
                missing.append(md_path.parent.name)
        assert not missing, (
            f"Engine agents missing model field:\n  " + "\n  ".join(missing)
        )

    def test_engine_agents_no_gpt4(self, agent_validator):
        """Engine agents: must not use gpt-4 (no guaranteed API key)."""
        engine_dir = WORKSPACE_ROOT / "aiPlat-core" / "core" / "engine" / "agents"
        if not engine_dir.exists():
            pytest.skip("No engine agents directory")
        violations = []
        for md_path in sorted(engine_dir.rglob("AGENT.md")):
            if "__pycache__" in str(md_path):
                continue
            raw = md_path.read_text(encoding="utf-8", errors="replace")
            if "gpt-4" in raw and "deepseek" not in raw:
                violations.append(md_path.parent.name)
        assert not violations, (
            f"Engine agents still using gpt-4:\n  " + "\n  ".join(violations)
        )

    def test_engine_agents_status_ready_or_running(self, agent_validator):
        """Engine agents: status should be 'ready' or 'running' (not 'stopped'/'initializing')."""
        engine_dir = WORKSPACE_ROOT / "aiPlat-core" / "core" / "engine" / "agents"
        if not engine_dir.exists():
            pytest.skip("No engine agents directory")
        bad = []
        for md_path in sorted(engine_dir.rglob("AGENT.md")):
            if "__pycache__" in str(md_path):
                continue
            raw = md_path.read_text(encoding="utf-8", errors="replace")
            import re
            m = re.search(r'^status:\s*(\S+)', raw, re.MULTILINE)
            if m and m.group(1) not in ("ready", "running"):
                bad.append(f"{md_path.parent.name}: status={m.group(1)}")
        assert not bad, (
            f"Engine agents with non-runnable status:\n  " + "\n  ".join(bad)
        )

    def test_no_control_characters_in_agent_md(self):
        """No AGENT.md file should contain control characters that break YAML parsing."""
        agents_dirs = [
            WORKSPACE_ROOT / "aiPlat-core" / "core" / "engine" / "agents",
            Path.home() / ".aiplat" / "agents",
        ]
        violations = []
        for agents_dir in agents_dirs:
            if not agents_dir.exists():
                continue
            for md_path in sorted(agents_dir.rglob("AGENT.md")):
                if "__pycache__" in str(md_path):
                    continue
                data = md_path.read_bytes()
                for i, b in enumerate(data):
                    if b < 0x20 and b not in (0x09, 0x0a, 0x0d):
                        violations.append(f"{md_path.parent.name}: byte 0x{b:02x} at pos {i}")
                        break
        assert not violations, (
            f"AGENT.md files with control characters:\n  " + "\n  ".join(violations)
        )
