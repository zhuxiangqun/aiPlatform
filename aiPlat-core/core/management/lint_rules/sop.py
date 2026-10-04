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


def _has_goal_signal(sop: str, skill: Any) -> bool:
    """Accept common goal/quality headings used by mature prompt skills."""
    if not sop:
        return False
    markers = (
        "## 目标", "# 目标", "目标：", "## 目的", "目的：",
        "输出铁律", "## 验收", "验收标准", "## Goal", "## Objective",
    )
    if any(m in sop for m in markers):
        return True
    meta = getattr(skill, "metadata", None) if not isinstance(skill, dict) else skill.get("metadata")
    if isinstance(meta, dict) and str(meta.get("completion_criterion") or "").strip():
        return True
    return False


def _has_checklist_signal(sop: str, skill: Any) -> bool:
    """Accept checklist / quality / iron-law sections and completion_criterion."""
    if not sop:
        return False
    markers = (
        "Checklist", "质量要求", "- [ ]",
        "输出铁律", "验收标准", "completion_criterion", "强制",
    )
    if any(m in sop for m in markers):
        return True
    meta = getattr(skill, "metadata", None) if not isinstance(skill, dict) else skill.get("metadata")
    if isinstance(meta, dict) and str(meta.get("completion_criterion") or "").strip():
        return True
    return False


class SopGoalCheck(LintRule):
    code = "sop_missing_goal"
    level = "warning"
    category = "sop"

    def check(self, skill: Any) -> List[LintIssue]:
        sop = _read_skill_md_body(skill)
        if sop and not _has_goal_signal(sop, skill):
            return [LintIssue(
                level=self.level, code=self.code,
                message='SOP 缺少"目标"章节/说明（建议补齐）',
                location="SKILL.md.body",
            )]
        return []


def _has_flow_signal(sop: str) -> bool:
    if not sop:
        return False
    markers = (
        "## SOP",
        "工作流程",
        "执行流程",
        "## 流程",
        "### 流程",
        "步骤",
        "Steps",
        "## Flow",
    )
    return any(m in sop for m in markers)


class SopFlowCheck(LintRule):
    code = "sop_missing_flow"
    level = "warning"
    category = "sop"

    def check(self, skill: Any) -> List[LintIssue]:
        sop = _read_skill_md_body(skill)
        if sop and not _has_flow_signal(sop):
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
        if sop and not _has_checklist_signal(sop, skill):
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
