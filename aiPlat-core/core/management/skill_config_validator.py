"""
SKILL.md configuration validator — catches YAML errors, missing fields, control characters.

Modeled on agent_config_validator.py. Validates all SKILL.md files at server startup.
"""

from __future__ import annotations

import os
import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class SkillConfigIssue:
    skill: str
    file: str
    severity: str  # "error" | "warn"
    message: str


REQUIRED_FIELDS = ["name"]
RECOMMENDED_FIELDS = ["display_name", "description", "category", "version", "status"]


def validate_skill_file(md_path: Path) -> List[SkillConfigIssue]:
    """Validate a single SKILL.md file. Returns list of issues."""
    issues: List[SkillConfigIssue] = []
    skill_name = md_path.parent.name
    file_path = str(md_path)

    try:
        raw = md_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return [SkillConfigIssue(skill=skill_name, file=file_path, severity="error",
                                message=f"Cannot read file: {e}")]

    # Control character check
    for i, ch in enumerate(raw):
        if ord(ch) < 0x20 and ch not in ("\t", "\n", "\r"):
            issues.append(SkillConfigIssue(
                skill=skill_name, file=file_path, severity="error",
                message=f"Control character 0x{ord(ch):02x} at position {i}"
            ))
            break

    # Parse frontmatter
    fm: dict = {}
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError as e:
                issues.append(SkillConfigIssue(
                    skill=skill_name, file=file_path, severity="error",
                    message=f"YAML parse error in frontmatter: {e}"
                ))
                return issues

    if not isinstance(fm, dict):
        issues.append(SkillConfigIssue(
            skill=skill_name, file=file_path, severity="error",
            message="Frontmatter missing or not a YAML mapping"
        ))
        return issues

    # Required fields
    for field in REQUIRED_FIELDS:
        if not fm.get(field):
            issues.append(SkillConfigIssue(
                skill=skill_name, file=file_path, severity="error",
                message=f"Missing required field: {field}"
            ))

    # Recommended fields
    for field in RECOMMENDED_FIELDS:
        if not fm.get(field):
            issues.append(SkillConfigIssue(
                skill=skill_name, file=file_path, severity="warn",
                message=f"Missing recommended field: {field}"
            ))

    # Status check
    status = fm.get("status", "")
    if status and status not in ("enabled", "disabled", "deprecated"):
        issues.append(SkillConfigIssue(
            skill=skill_name, file=file_path, severity="warn",
            message=f"Unrecognized status value: '{status}' (expected enabled|disabled|deprecated)"
        ))

    return issues


def validate_all_skills(skills_dir: str) -> Tuple[List[SkillConfigIssue], List[SkillConfigIssue]]:
    """Validate all SKILL.md files in a directory tree (recursive).
    Returns (errors, warnings).
    """
    errors: List[SkillConfigIssue] = []
    warnings: List[SkillConfigIssue] = []
    base = Path(skills_dir)
    if not base.exists():
        return errors, warnings

    for md_path in sorted(base.rglob("SKILL.md")):
        if "__pycache__" in str(md_path):
            continue
        for issue in validate_skill_file(md_path):
            if issue.severity == "error":
                errors.append(issue)
            else:
                warnings.append(issue)

    return errors, warnings
