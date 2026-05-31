"""Lint rules: permissions, high-risk constraints, required questions."""

from typing import Any, List

from core.management.skill_linter_base import LintIssue, LintRule


class PermissionsCheck(LintRule):
    code = "missing_permissions"
    level = "error"
    category = "governance"

    def check(self, skill: Any) -> List[LintIssue]:
        meta = self._get_meta(skill)
        executable = bool(meta.get("executable") is True) or str(meta.get("skill_kind") or "").lower() == "executable"
        perms = self._as_list(meta.get("permissions") or meta.get("permission"))
        if executable and not perms:
            return [LintIssue(
                level=self.level, code=self.code,
                message="executable skill 必须声明 permissions（至少 llm:generate）",
                location="frontmatter.permissions",
            )]
        return []

    @staticmethod
    def _get_meta(skill: Any) -> dict:
        meta = getattr(skill, "metadata", None) if not isinstance(skill, dict) else skill.get("metadata")
        return meta if isinstance(meta, dict) else {}


class HighRiskConstraintsCheck(LintRule):
    code = "high_risk_missing_constraints"
    level = "warning"
    category = "governance"

    _CONSTRAINT_MARKERS = ("批量", "删除", "覆盖", "不可逆", "生产", "回滚", "审批", "权限", "stable", "canary")

    def check(self, skill: Any) -> List[LintIssue]:
        meta = self._get_meta(skill)
        perms = self._as_list(meta.get("permissions") or meta.get("permission"))
        risk = self._risk_level(perms)
        if risk != "high":
            return []

        desc = str(getattr(skill, "description", "") or (skill.get("description") if isinstance(skill, dict) else "") or "").strip()
        tc = self._as_list(meta.get("trigger_conditions") or meta.get("trigger_keywords"))
        tc_text = " ".join(tc)
        keywords = meta.get("keywords") if isinstance(meta.get("keywords"), dict) else {}
        kw_constraints = self._as_list((keywords or {}).get("constraints"))

        constraint_hit = any(k in tc_text or k in desc for k in kw_constraints) if kw_constraints else False
        constraint_hit = constraint_hit or any(m in tc_text or m in desc for m in self._CONSTRAINT_MARKERS)

        if not constraint_hit:
            return [LintIssue(
                level=self.level, code=self.code,
                message="高风险权限 Skill 建议在 trigger_conditions/description 中加入约束词（批量/删除/生产/不可逆/回滚等）以提升稳定召回并降低误触发",
                location="frontmatter.trigger_conditions",
            )]
        return []

    @staticmethod
    def _get_meta(skill: Any) -> dict:
        meta = getattr(skill, "metadata", None) if not isinstance(skill, dict) else skill.get("metadata")
        return meta if isinstance(meta, dict) else {}

    @staticmethod
    def _risk_level(perms: List[str]) -> str:
        from core.management.skill_linter import risk_level_from_permissions
        return risk_level_from_permissions(perms)


class RequiredQuestionsCheck(LintRule):
    code = "missing_required_questions"
    level = "warning"
    category = "governance"

    def check(self, skill: Any) -> List[LintIssue]:
        meta = self._get_meta(skill)
        perms = self._as_list(meta.get("permissions") or meta.get("permission"))
        risk = self._risk_level(perms)
        if risk != "high":
            return []

        executable = bool(meta.get("executable") is True) or str(meta.get("skill_kind") or "").lower() == "executable"
        required_questions = self._as_list(meta.get("required_questions"))

        if executable and not required_questions:
            return [LintIssue(
                level=self.level, code=self.code,
                message="高风险可执行 Skill 建议填写 required_questions（缺参追问清单），否则模型容易不敢触发或触发后不会用",
                location="frontmatter.required_questions",
            )]
        return []

    @staticmethod
    def _get_meta(skill: Any) -> dict:
        meta = getattr(skill, "metadata", None) if not isinstance(skill, dict) else skill.get("metadata")
        return meta if isinstance(meta, dict) else {}

    @staticmethod
    def _risk_level(perms: List[str]) -> str:
        from core.management.skill_linter import risk_level_from_permissions
        return risk_level_from_permissions(perms)
