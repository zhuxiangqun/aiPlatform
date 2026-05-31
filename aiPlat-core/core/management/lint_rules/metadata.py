"""Lint rule: generic name detection."""

import re
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
