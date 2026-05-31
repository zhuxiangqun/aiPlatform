"""Lint rules: trigger quality, keywords, description signals, negative triggers, routing disambiguation."""

from typing import Any, Dict, List

from core.management.skill_linter_base import LintIssue, LintRule


class TriggerTooFewCheck(LintRule):
    code = "triggers_too_few"
    level = "warning"
    category = "trigger"

    def check(self, skill: Any) -> List[LintIssue]:
        meta = self._get_meta(skill)
        tc = self._as_list(meta.get("trigger_conditions") or meta.get("trigger_keywords"))
        if tc and len(tc) < 6:
            return [LintIssue(
                level=self.level, code=self.code,
                message="trigger_conditions 建议 6-12 条（覆盖口语/同义表达/约束词），以提升命中率与稳定性",
                location="frontmatter.trigger_conditions",
            )]
        return []

    @staticmethod
    def _get_meta(skill: Any) -> dict:
        meta = getattr(skill, "metadata", None) if not isinstance(skill, dict) else skill.get("metadata")
        return meta if isinstance(meta, dict) else {}


class MissingKeywordsCheck(LintRule):
    code = "missing_keywords"
    level = "warning"
    category = "trigger"

    def check(self, skill: Any) -> List[LintIssue]:
        meta = self._get_meta(skill)
        keywords = meta.get("keywords") if isinstance(meta.get("keywords"), dict) else {}
        kw_objects = self._as_list((keywords or {}).get("objects"))
        kw_actions = self._as_list((keywords or {}).get("actions"))
        if not kw_objects or not kw_actions:
            return [LintIssue(
                level=self.level, code=self.code,
                message="建议填写 keywords.objects/actions/constraints（对象词/动作词/约束词），用于提升召回与区分度",
                location="frontmatter.keywords",
            )]
        return []

    @staticmethod
    def _get_meta(skill: Any) -> dict:
        meta = getattr(skill, "metadata", None) if not isinstance(skill, dict) else skill.get("metadata")
        return meta if isinstance(meta, dict) else {}


class GenericDescriptionCheck(LintRule):
    code = "generic_description"
    level = "warning"
    category = "trigger"

    _BUILTIN_OBJECTS = ("代码", "sql", "日志", "合同", "发票", "订单", "pdf", "csv", "表格", "权限", "schema", "配置", "报错", "接口", "数据库")
    _BUILTIN_ACTIONS = ("审查", "排查", "优化", "生成", "转换", "对账", "导出", "review", "analyze", "generate", "fix")

    def check(self, skill: Any) -> List[LintIssue]:
        desc = str(getattr(skill, "description", "") or (skill.get("description") if isinstance(skill, dict) else "") or "").strip()
        if not desc:
            return []

        meta = self._get_meta(skill)
        keywords = meta.get("keywords") if isinstance(meta.get("keywords"), dict) else {}
        kw_objects = self._as_list((keywords or {}).get("objects"))
        kw_actions = self._as_list((keywords or {}).get("actions"))

        has_obj = any(k.lower() in desc.lower() for k in kw_objects) if kw_objects else any(m in desc.lower() for m in self._BUILTIN_OBJECTS)
        has_act = any(k.lower() in desc.lower() for k in kw_actions) if kw_actions else any(m in desc.lower() for m in self._BUILTIN_ACTIONS)

        if not has_obj or not has_act:
            return [LintIssue(
                level=self.level, code=self.code,
                message='description 过泛或缺少对象词/动作词；建议补充"触发场景+动作+对象+输出+不适用"并补齐关键词',
                location="frontmatter.description",
            )]
        return []

    @staticmethod
    def _get_meta(skill: Any) -> dict:
        meta = getattr(skill, "metadata", None) if not isinstance(skill, dict) else skill.get("metadata")
        return meta if isinstance(meta, dict) else {}


class MissingNegativeTriggersCheck(LintRule):
    code = "missing_negative_triggers"
    level = "warning"
    category = "trigger"

    def check(self, skill: Any) -> List[LintIssue]:
        desc = str(getattr(skill, "description", "") or (skill.get("description") if isinstance(skill, dict) else "") or "").strip()
        meta = self._get_meta(skill)
        negative_triggers = self._as_list(meta.get("negative_triggers"))
        tc = self._as_list(meta.get("trigger_conditions") or meta.get("trigger_keywords"))
        if (not negative_triggers) and desc and ("不" not in desc) and tc:
            return [LintIssue(
                level=self.level, code=self.code,
                message='建议补充 negative_triggers 或在 description 中写明"不适用于..."，以减少误触发',
                location="frontmatter.negative_triggers",
            )]
        return []

    @staticmethod
    def _get_meta(skill: Any) -> dict:
        meta = getattr(skill, "metadata", None) if not isinstance(skill, dict) else skill.get("metadata")
        return meta if isinstance(meta, dict) else {}


class RoutingDisambigCheck(LintRule):
    code = "routing_needs_disambiguation"
    level = "warning"
    category = "trigger"

    def check(self, skill: Any) -> List[LintIssue]:
        meta = self._get_meta(skill)
        obs = meta.get("_observability") if isinstance(meta.get("_observability"), dict) else None
        if not obs:
            return []
        try:
            wrong_top1 = int(obs.get("selected_not_top1") or 0)
            wrong_cand = int(obs.get("selected_not_in_candidates") or 0)
            avg_rank = obs.get("selected_rank_avg")
            rank_ge3 = int(obs.get("selected_rank_ge3") or 0)
            sel = int(obs.get("selected") or 0)
            if sel >= 10 and (wrong_top1 >= 3 or wrong_cand >= 1 or rank_ge3 >= 3 or (isinstance(avg_rank, (int, float)) and float(avg_rank) >= 2.0)):
                return [LintIssue(
                    level=self.level, code=self.code,
                    message=f"路由质量提示：selected={sel}, wrong_top1={wrong_top1}, wrong_cand={wrong_cand}, avg_rank={avg_rank}, rank>=3={rank_ge3}。建议补充 constraints/negative_triggers 提高区分度。",
                    location="observability.routing_funnel",
                )]
        except Exception:
            pass
        return []

    @staticmethod
    def _get_meta(skill: Any) -> dict:
        meta = getattr(skill, "metadata", None) if not isinstance(skill, dict) else skill.get("metadata")
        return meta if isinstance(meta, dict) else {}
