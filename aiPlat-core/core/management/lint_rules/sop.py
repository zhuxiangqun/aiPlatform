"""Lint rules: SOP body quality checks."""

from typing import Any, List
from pathlib import Path

from core.management.skill_linter_base import LintIssue, LintRule


def _read_skill_md_body(skill: Any) -> str:
    """Best-effort: read SKILL.md body via skill.metadata.filesystem.skill_md."""
    try:
        meta = getattr(skill, "metadata", None) if not isinstance(skill, dict) else (skill.get("metadata") if isinstance(skill.get("metadata"), dict) else {})
        fs = meta.get("filesystem") if isinstance(meta, dict) and isinstance(meta.get("filesystem"), dict) else {}
        p = fs.get("skill_md")
        if not p:
            return ""
        raw = Path(str(p)).read_text(encoding="utf-8")
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                return (parts[2] or "").strip()
        return raw.strip()
    except Exception:
        return ""


class SopGoalCheck(LintRule):
    code = "sop_missing_goal"
    level = "warning"
    category = "sop"

    def check(self, skill: Any) -> List[LintIssue]:
        sop = _read_skill_md_body(skill)
        if sop and not (("## 目标" in sop) or ("# 目标" in sop) or ("目标：" in sop)):
            return [LintIssue(
                level=self.level, code=self.code,
                message='SOP 缺少"目标"章节/说明（建议补齐）',
                location="SKILL.md.body",
            )]
        return []


class SopFlowCheck(LintRule):
    code = "sop_missing_flow"
    level = "warning"
    category = "sop"

    def check(self, skill: Any) -> List[LintIssue]:
        sop = _read_skill_md_body(skill)
        if sop and not (("## SOP" in sop) or ("工作流程" in sop) or ("步骤" in sop)):
            return [LintIssue(
                level=self.level, code=self.code,
                message='SOP 缺少"流程/步骤"章节（建议补齐）',
                location="SKILL.md.body",
            )]
        return []


class SopChecklistCheck(LintRule):
    code = "sop_missing_checklist"
    level = "warning"
    category = "sop"

    def check(self, skill: Any) -> List[LintIssue]:
        sop = _read_skill_md_body(skill)
        if sop and not (("Checklist" in sop) or ("质量要求" in sop) or ("- [ ]" in sop)):
            return [LintIssue(
                level=self.level, code=self.code,
                message="SOP 缺少 Checklist/质量要求（建议补齐以便回归测试）",
                location="SKILL.md.body",
            )]
        return []


class SopBodyCheck(LintRule):
    code = "missing_sop_body"
    level = "warning"
    category = "sop"

    def check(self, skill: Any) -> List[LintIssue]:
        sop = _read_skill_md_body(skill)
        if not sop:
            return [LintIssue(
                level=self.level, code=self.code,
                message="无法读取 SKILL.md 正文（SOP），建议检查 filesystem.skill_md 路径",
                location="SKILL.md",
            )]
        return []
