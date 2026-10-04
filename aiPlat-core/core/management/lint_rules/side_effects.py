"""Lint: prompt skills must not declare mutating effects without a handler."""
from typing import Any, List, Optional

from core.harness.execution.skill_side_effect_gate import unrealized_side_effect_reason
from core.management.skill_linter_base import FixProposal, LintIssue, LintRule


class UnrealizedSideEffectCheck(LintRule):
    code = "unrealized_side_effect"
    level = "error"
    category = "metadata"
    scope = ["skill"]

    def check(self, skill: Any) -> List[LintIssue]:
        reason = unrealized_side_effect_reason(skill)
        if not reason:
            return []
        return [
            LintIssue(
                level=self.level,
                code=self.code,
                message=reason,
                location="frontmatter.effects",
            )
        ]

    def propose_fix(self, skill: Any, issue: LintIssue) -> Optional[FixProposal]:
        return FixProposal(
            fix_id="fix_unrealized_side_effect",
            issue_code=self.code,
            title="副作用必须有 handler，或把 effects 改为 emit（禁止一键编造写盘）",
            priority="P0",
            risk_level="high",
            auto_applicable=False,
            requires_approval=True,
            touches=["SKILL.md.frontmatter.execution_type", "handler.py"],
            ops=[],
            preview={
                "before_snippet": issue.message or "",
                "after_snippet": (
                    "Add handler.py that calls an existing tool/syscall, "
                    "set execution_type: handler; or change mutating effects to type: emit."
                ),
            },
            markdown=(
                "### 假执行\n"
                "- prompt 只能产出文本。\n"
                "- 写文件/网络/执行命令必须有 handler.py，并走已有 tool/syscall。\n"
                "- 一键修复不会生成假 handler 或假 URL。\n"
            ),
        )
