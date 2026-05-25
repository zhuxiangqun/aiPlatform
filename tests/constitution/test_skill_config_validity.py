"""
Constitution test: SKILL.md configuration validity.

Ensures all SKILL.md files (engine) are well-formed YAML and have required fields.
"""

import os
import sys
from pathlib import Path

_CORE_DIR = Path(__file__).resolve().parents[2] / "aiPlat-core"
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


class TestSkillConfigValidity:
    """All SKILL.md files must parse without YAML errors and have required fields."""

    def test_engine_skills_yaml_valid(self):
        """Engine skills: YAML frontmatter must parse without errors."""
        from core.management.skill_config_validator import validate_skill_file
        skills_dir = WORKSPACE_ROOT / "aiPlat-core" / "core" / "engine" / "skills"
        if not skills_dir.exists():
            pytest.skip("No engine skills directory")
        errors = []
        for md_path in sorted(skills_dir.rglob("SKILL.md")):
            if "__pycache__" in str(md_path):
                continue
            for issue in validate_skill_file(md_path):
                if issue.severity == "error":
                    errors.append(f"{md_path.parent.name}: {issue.message}")
        assert not errors, (
            f"Engine SKILL.md parse errors:\n  " + "\n  ".join(errors)
        )

    def test_engine_skills_have_name(self):
        """Engine skills: must have 'name' field configured."""
        skills_dir = WORKSPACE_ROOT / "aiPlat-core" / "core" / "engine" / "skills"
        if not skills_dir.exists():
            pytest.skip("No engine skills directory")
        missing = []
        for md_path in sorted(skills_dir.rglob("SKILL.md")):
            if "__pycache__" in str(md_path):
                continue
            raw = md_path.read_text(encoding="utf-8", errors="replace")
            if "name:" not in raw:
                missing.append(md_path.parent.name)
        assert not missing, (
            f"Engine skills missing name field:\n  " + "\n  ".join(missing)
        )

    def test_engine_skills_have_description(self):
        """Engine skills: must have 'description' field (recommended)."""
        skills_dir = WORKSPACE_ROOT / "aiPlat-core" / "core" / "engine" / "skills"
        if not skills_dir.exists():
            pytest.skip("No engine skills directory")
        missing = []
        for md_path in sorted(skills_dir.rglob("SKILL.md")):
            if "__pycache__" in str(md_path):
                continue
            raw = md_path.read_text(encoding="utf-8", errors="replace")
            if "description:" not in raw:
                missing.append(md_path.parent.name)
        assert not missing, (
            f"Engine skills missing description (recommended):\n  " + "\n  ".join(missing)
        )

    def test_engine_skills_status_valid(self):
        """Engine skills: status must be enabled|disabled|deprecated."""
        import re
        skills_dir = WORKSPACE_ROOT / "aiPlat-core" / "core" / "engine" / "skills"
        if not skills_dir.exists():
            pytest.skip("No engine skills directory")
        bad = []
        for md_path in sorted(skills_dir.rglob("SKILL.md")):
            if "__pycache__" in str(md_path):
                continue
            raw = md_path.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'^status:\s*(\S+)', raw, re.MULTILINE)
            if m and m.group(1) not in ("enabled", "disabled", "deprecated", "test_fixture"):
                bad.append(f"{md_path.parent.name}: status={m.group(1)}")
        assert not bad, (
            f"Engine skills with invalid status:\n  " + "\n  ".join(bad)
        )

    def test_skills_no_control_characters(self):
        """No SKILL.md file should contain control characters."""
        skills_dir = WORKSPACE_ROOT / "aiPlat-core" / "core" / "engine" / "skills"
        if not skills_dir.exists():
            pytest.skip("No engine skills directory")
        violations = []
        for md_path in sorted(skills_dir.rglob("SKILL.md")):
            if "__pycache__" in str(md_path):
                continue
            data = md_path.read_bytes()
            for i, b in enumerate(data):
                if b < 0x20 and b not in (0x09, 0x0a, 0x0d):
                    violations.append(f"{md_path.parent.name}: byte 0x{b:02x} at pos {i}")
                    break
        assert not violations, (
            f"SKILL.md files with control characters:\n  " + "\n  ".join(violations)
        )
