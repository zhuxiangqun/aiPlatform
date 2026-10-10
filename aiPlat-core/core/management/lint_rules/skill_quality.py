"""Lint rules: Skill quality — no-ops, misplaced FILE criteria, invocation_mode."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Set

from core.management.skill_linter_base import LintIssue, LintRule

_NOOP_PHRASES = (
    "高质量",
    "遵循最佳实践",
    "要彻底",
    "尽可能完善",
    "写得清晰",
    "easy to read",
    "be thorough",
    "输出格式符合规范",
    "正确处理错误和边界条件",
    "返回结果包含引用和来源标注",
)

_FILE_MARKERS = ("## FILE:", "完整可运行代码", "所有依赖项已声明")

_FILE_OK_NAMES: Set[str] = {
    "code_generation",
    "eval_code_generator",
    "app_page_generation",
    "package_builder",
    "test_case_generation",
    "test_executor",
    "e2e_test",
    "code-hygiene",
}


def _meta(skill: Any) -> dict:
    meta = getattr(skill, "metadata", None) if not isinstance(skill, dict) else skill.get("metadata")
    return meta if isinstance(meta, dict) else {}


def _name(skill: Any) -> str:
    if isinstance(skill, dict):
        return str(skill.get("name") or skill.get("id") or skill.get("skill_id") or "").strip()
    return str(
        getattr(skill, "name", None)
        or getattr(skill, "id", None)
        or (_meta(skill).get("name") if _meta(skill) else "")
        or ""
    ).strip()


def _read_body(skill: Any) -> str:
    try:
        meta = _meta(skill)
        fs = meta.get("filesystem") if isinstance(meta.get("filesystem"), dict) else {}
        p = fs.get("skill_md")
        if not p:
            return str(meta.get("body") or meta.get("sop") or "")
        raw = Path(str(p)).read_text(encoding="utf-8")
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            return (parts[2] if len(parts) >= 3 else raw).strip()
        return raw.strip()
    except Exception:
        return ""


def _uses_file_output(skill: Any) -> bool:
    meta = _meta(skill)
    if bool(meta.get("uses_file_output")):
        return True
    name = _name(skill)
    return name in _FILE_OK_NAMES


def _invocation_mode(skill: Any) -> str:
    meta = _meta(skill)
    mode = str(meta.get("invocation_mode") or "").strip().lower()
    if mode in ("user", "auto"):
        return mode
    if meta.get("auto_trigger_allowed") is False:
        return "user"
    if isinstance(skill, dict):
        m2 = str(skill.get("invocation_mode") or "").strip().lower()
        if m2 in ("user", "auto"):
            return m2
    return "auto"


class SkillNoOpPhrasesCheck(LintRule):
    """Flag adjective / boilerplate lines that do not change model behavior."""

    code = "skill_noop_phrases"
    level = "warning"
    category = "sop"
    scope = ["skill"]

    def check(self, skill: Any) -> List[LintIssue]:
        # Only SOP goal/criterion/body — skip_when may legitimately mention 最佳实践
        blob = " ".join(
            [
                str(_meta(skill).get("sop_goal") or ""),
                str(_meta(skill).get("completion_criterion") or ""),
                _read_body(skill),
            ]
        )
        hits = [p for p in _NOOP_PHRASES if p.lower() in blob.lower()]
        if not hits:
            return []
        return [
            LintIssue(
                level=self.level,
                code=self.code,
                message=(
                    "疑似 no-op / 空话："
                    + "、".join(hits[:6])
                    + "。删掉后若输出不变则删除；改用可验证验收（字段/格式/命令）"
                ),
                location="SKILL.md.body",
            )
        ]


class MisplacedFileCompletionCheck(LintRule):
    """Non-codegen skills must not require ## FILE: completion criteria."""

    code = "misplaced_file_completion"
    level = "warning"
    category = "sop"
    scope = ["skill"]

    def check(self, skill: Any) -> List[LintIssue]:
        if _uses_file_output(skill):
            return []
        crit = str(_meta(skill).get("completion_criterion") or "")
        if not crit and isinstance(skill, dict):
            crit = str(skill.get("completion_criterion") or "")
        if any(m in crit for m in _FILE_MARKERS):
            return [
                LintIssue(
                    level=self.level,
                    code=self.code,
                    message="completion_criterion 误用 ## FILE:/可运行代码模板；请改为与本技能目标一致的可验收条件",
                    location="frontmatter.completion_criterion",
                )
            ]
        return []


class InvocationModeCheck(LintRule):
    """Validate invocation_mode and keep it aligned with auto_trigger_allowed."""

    code = "invocation_mode_invalid"
    level = "warning"
    category = "governance"
    scope = ["skill"]

    def check(self, skill: Any) -> List[LintIssue]:
        meta = _meta(skill)
        mode = str(meta.get("invocation_mode") or (skill.get("invocation_mode") if isinstance(skill, dict) else "") or "").strip().lower()
        if not mode:
            return []
        if mode not in ("user", "auto"):
            return [
                LintIssue(
                    level=self.level,
                    code=self.code,
                    message="invocation_mode 仅允许 user|auto",
                    location="frontmatter.invocation_mode",
                )
            ]
        ata = meta.get("auto_trigger_allowed")
        if ata is None and isinstance(skill, dict):
            ata = skill.get("auto_trigger_allowed")
        if ata is None:
            return []
        if mode == "user" and bool(ata) is True:
            return [
                LintIssue(
                    level=self.level,
                    code="invocation_mode_conflict",
                    message="invocation_mode=user 时应设 auto_trigger_allowed: false（否则仍会被自动路由）",
                    location="frontmatter.auto_trigger_allowed",
                )
            ]
        if mode == "auto" and bool(ata) is False:
            return [
                LintIssue(
                    level=self.level,
                    code="invocation_mode_conflict",
                    message="invocation_mode=auto 与 auto_trigger_allowed=false 冲突",
                    location="frontmatter.auto_trigger_allowed",
                )
            ]
        return []


class UserModeTriggerSoftPass(LintRule):
    """Document-only: user-invoked skills need not pad trigger_conditions."""

    code = "user_mode_triggers_optional"
    level = "info"
    category = "trigger"
    scope = ["skill"]

    def check(self, skill: Any) -> List[LintIssue]:
        if _invocation_mode(skill) != "user":
            return []
        meta = _meta(skill)
        tc = meta.get("trigger_conditions") or meta.get("triggers") or []
        if isinstance(skill, dict) and not tc:
            tc = skill.get("trigger_conditions") or skill.get("triggers") or []
        n = len(tc) if isinstance(tc, list) else 0
        if n >= 3:
            return []
        return [
            LintIssue(
                level=self.level,
                code=self.code,
                message="invocation_mode=user：触发短语可选（不进自动路由）；需要检索时再补 trigger_conditions",
                location="frontmatter.trigger_conditions",
            )
        ]
