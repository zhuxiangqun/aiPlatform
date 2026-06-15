"""Lint rules: change contract, markdown schema, markdown required."""

from typing import Any, List

from core.management.skill_linter_base import LintIssue, LintRule


class ChangeContractCheck(LintRule):
    code = "missing_change_contract"
    level = "warning"
    category = "schema"
    scope = ["skill"]

    _REQUIRED_KEYS = ["change_plan", "changed_files", "unrelated_changes", "acceptance_criteria", "rollback_plan"]

    def check(self, skill: Any) -> List[LintIssue]:
        category = str(getattr(skill, "type", "") or (skill.get("category") if isinstance(skill, dict) else "") or "").strip()
        meta = self._get_meta(skill)
        executable = bool(meta.get("executable") is True) or str(meta.get("skill_kind") or "").lower() == "executable"
        tags = meta.get("tags") or []
        tags = [str(t).strip().lower() for t in tags] if isinstance(tags, list) else []
        is_coding = category.lower() == "coding" or ("coding" in tags) or ("code" in tags)

        if not (is_coding or executable):
            return []

        output_schema = getattr(skill, "output_schema", None) if not isinstance(skill, dict) else skill.get("output_schema")
        if not isinstance(output_schema, dict) or not output_schema:
            return []

        missing = [k for k in self._REQUIRED_KEYS if k not in output_schema]
        if missing:
            return [LintIssue(
                level=self.level, code=self.code,
                message="建议为 coding/executable Skill 补齐输出契约字段（用于精准修改/验收/回滚）：" + ",".join(missing),
                location="frontmatter.output_schema",
            )]
        return []

    @staticmethod
    def _get_meta(skill: Any) -> dict:
        meta = getattr(skill, "metadata", None) if not isinstance(skill, dict) else skill.get("metadata")
        return meta if isinstance(meta, dict) else {}


class MarkdownSchemaCheck(LintRule):
    code = "invalid_markdown_schema"
    level = "error"
    category = "schema"
    scope = ["skill"]

    def check(self, skill: Any) -> List[LintIssue]:
        output_schema = getattr(skill, "output_schema", None) if not isinstance(skill, dict) else skill.get("output_schema")
        if not isinstance(output_schema, dict) or not output_schema:
            return []
        if "markdown" not in output_schema:
            return []
        md = output_schema.get("markdown")
        if not isinstance(md, dict):
            return [LintIssue(
                level=self.level, code=self.code,
                message="output_schema.markdown 必须是对象 schema",
                location="frontmatter.output_schema.markdown",
            )]
        return []


class MarkdownRequiredCheck(LintRule):
    code = "markdown_required"
    level = "warning"
    category = "schema"
    scope = ["skill"]

    def check(self, skill: Any) -> List[LintIssue]:
        output_schema = getattr(skill, "output_schema", None) if not isinstance(skill, dict) else skill.get("output_schema")
        if not isinstance(output_schema, dict) or not output_schema:
            return []
        md = output_schema.get("markdown")
        if not isinstance(md, dict):
            return []
        if md.get("required") is not True:
            return [LintIssue(
                level=self.level, code=self.code,
                message="建议 output_schema.markdown.required=true（平台统一要求）",
                location="frontmatter.output_schema.markdown.required",
            )]
        return []


class MarkdownTypeCheck(LintRule):
    code = "markdown_type"
    level = "error"
    category = "schema"
    scope = ["skill"]

    def check(self, skill: Any) -> List[LintIssue]:
        output_schema = getattr(skill, "output_schema", None) if not isinstance(skill, dict) else skill.get("output_schema")
        if not isinstance(output_schema, dict) or not output_schema:
            return []
        md = output_schema.get("markdown")
        if not isinstance(md, dict):
            return []
        t = str(md.get("type") or "").strip().lower()
        if t and t != "string":
            return [LintIssue(
                level=self.level, code=self.code,
                message="output_schema.markdown.type 必须为 string",
                location="frontmatter.output_schema.markdown.type",
            )]
        return []
