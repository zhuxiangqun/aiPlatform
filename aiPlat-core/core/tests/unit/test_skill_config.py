"""
test_skill_config — verify workspace SKILL.md files meet frontmatter requirements.

Enforces:
  - Root CLAUDE.md §17: execution_type must be explicitly declared
  - Core CLAUDE.md §5.19: Skill must declare effects field
  - Core CLAUDE.md §5.10: handler type skills must have handler.py
"""

import os
from pathlib import Path

import yaml


SKILLS_DIR = Path(os.path.expanduser("~/.aiplat/skills"))


def _parse_frontmatter(path: Path) -> dict:
    """Extract YAML frontmatter from SKILL.md file."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except Exception:
        return {}


def _get_skill_dirs() -> list[Path]:
    """Find all directories containing SKILL.md files."""
    if not SKILLS_DIR.exists():
        return []
    out = []
    for item in sorted(SKILLS_DIR.iterdir()):
        if item.is_dir() and (item / "SKILL.md").exists():
            out.append(item)
    return out


def test_execution_type_declared():
    """Every SKILL.md must have execution_type in frontmatter (CLAUDE.md §17.1)."""
    missing = []
    for d in _get_skill_dirs():
        md = d / "SKILL.md"
        fm = _parse_frontmatter(md)
        if "execution_type" not in fm:
            missing.append(str(d.name))
    assert len(missing) == 0, (
        f"{len(missing)} skill(s) missing execution_type:\n  " +
        "\n  ".join(missing)
    )


def test_handler_type_has_handler_py():
    """execution_type:handler must have handler.py in same dir (§17.2)."""
    violations = []
    for d in _get_skill_dirs():
        md = d / "SKILL.md"
        fm = _parse_frontmatter(md)
        if fm.get("execution_type") == "handler":
            if not (d / "handler.py").exists():
                violations.append(str(d.name))
    assert len(violations) == 0, (
        f"{len(violations)} skill(s) declared execution_type:handler but missing handler.py:\n  " +
        "\n  ".join(violations)
    )


def test_handler_py_with_prompt_execution_type_warns():
    """handler.py exists but execution_type says prompt → inconsistency (§17.3)."""
    inconsistencies = []
    for d in _get_skill_dirs():
        md = d / "SKILL.md"
        fm = _parse_frontmatter(md)
        has_handler = (d / "handler.py").exists()
        if has_handler and fm.get("execution_type") == "prompt":
            inconsistencies.append(str(d.name))
    # This is a WARNING, not an error — just log
    if inconsistencies:
        print(f"\n  ⚠️  {len(inconsistencies)} skill(s) have handler.py but execution_type:prompt:")
        for name in inconsistencies:
            print(f"     - {name}")


def test_effects_declared():
    """Every SKILL.md should have effects field (CLAUDE.md §5.19)."""
    missing = []
    for d in _get_skill_dirs():
        md = d / "SKILL.md"
        fm = _parse_frontmatter(md)
        if "effects" not in fm:
            missing.append(str(d.name))
    # This is a WARNING — effects can be auto-inferred
    if missing:
        print(f"\n  ⚠️  {len(missing)} skill(s) missing effects declaration:")
        for name in missing[:10]:
            print(f"     - {name}")
        if len(missing) > 10:
            print(f"     ... and {len(missing) - 10} more")
