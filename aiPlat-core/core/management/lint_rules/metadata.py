"""Lint rule: generic name detection, execution_type/directory mismatch, nested structure."""

import os
import re
from pathlib import Path
from typing import Any, List

from core.management.skill_linter_base import LintIssue, LintRule


class GenericNameCheck(LintRule):
    code = "generic_name"
    level = "warning"
    category = "metadata"

    _MARKERS = ("tool", "assistant", "helper", "my-", "skill-")

    def check(self, skill: Any) -> List[LintIssue]:
        name = str(getattr(skill, "name", "") or (skill.get("name") if isinstance(skill, dict) else "") or "").strip().lower()
        if name and any(m in name for m in self._MARKERS):
            return [LintIssue(
                level=self.level, code=self.code,
                message='Skill 名称过泛，容易与其它 Skill 冲突导致误触发/不触发；建议使用"动词+名词(+限定)"',
                location="frontmatter.name",
            )]
        return []


class ExecTypeDirectoryMismatch(LintRule):
    """Check that execution_type declaration matches actual directory content."""
    code = "exec_type_dir_mismatch"
    level = "error"
    category = "metadata"

    def check(self, skill: Any) -> List[LintIssue]:
        issues: List[LintIssue] = []
        exec_type = str(getattr(skill, "execution_type", "") or "").strip().lower()
        skill_dir = self._resolve_skill_dir(skill)
        if not skill_dir:
            return issues

        root = Path(skill_dir)
        has_handler = (root / "handler.py").exists()
        has_scripts = (root / "scripts").is_dir() and bool(list((root / "scripts").glob("*.py")))

        if exec_type == "handler" and not has_handler:
            issues.append(LintIssue(
                level=self.level, code=self.code,
                message=f"execution_type=handler but handler.py not found in {skill_dir}",
                location="frontmatter.execution_type",
            ))
        if has_scripts and exec_type == "prompt":
            issues.append(LintIssue(
                level="warning", code=self.code,
                message=f"scripts/ directory has .py files but execution_type=prompt (should be handler or hybrid)",
                location="frontmatter.execution_type",
            ))
        return issues

    @staticmethod
    def _resolve_skill_dir(skill: Any) -> str:
        md = getattr(skill, "metadata", {}) or {}
        if isinstance(md, dict):
            for k in ("skill_dir", "fs", "filesystem"):
                v = md.get(k)
                if isinstance(v, str) and os.path.isdir(v):
                    return v
                if isinstance(v, dict):
                    d = v.get("skill_dir") or v.get("root") or v.get("path")
                    if isinstance(d, str) and os.path.isdir(d):
                        return d
        cfg = getattr(skill, "_config", None)
        if cfg:
            meta = getattr(cfg, "metadata", {}) or {}
            if isinstance(meta, dict):
                d = meta.get("skill_dir")
                if isinstance(d, str) and os.path.isdir(d):
                    return d
        return ""


class NestedSkillDirectory(LintRule):
    """Detect nested skills/<name>/ structure (Path B zip import artifact)."""
    code = "nested_skill_dir"
    level = "error"
    category = "metadata"

    def check(self, skill: Any) -> List[LintIssue]:
        skill_dir = ExecTypeDirectoryMismatch._resolve_skill_dir(skill)
        if not skill_dir:
            return []

        root = Path(skill_dir)
        name = str(getattr(skill, "name", "") or root.name)
        nested = root / "skills" / name

        if nested.is_dir():
            # Count SKILL.md files found at nested paths
            nested_skill_mds = list(root.rglob("SKILL.md"))
            nested_count = sum(1 for p in nested_skill_mds if p.parent != root)
            return [LintIssue(
                level=self.level, code=self.code,
                message=f"Detected nested skills/{name}/ directory structure from broken zip import. "
                        f"Found {nested_count} SKILL.md at non-root paths. "
                        f"Re-import via the installer or run adapt_skill() to fix.",
                location=str(nested),
            )]
        return []
