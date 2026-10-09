"""invocation_mode / auto_trigger_allowed — user skills skip auto routing."""

from __future__ import annotations

import tempfile
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[3]
import sys

sys.path.insert(0, str(CORE_ROOT))

from core.apps.skills.discovery import SKILLMD_parser, SkillMatcher
from core.harness.routing.skill_routing import compute_skill_candidates
from core.apps.skills.contract import build_contract_and_digest


USER_SKILL = """---
name: my_personal_process
description: 个人流程技能，仅用户点名
invocation_mode: user
triggers:
  - 个人流程
  - 点名调用
---

# SOP
1. 做一件可验收的事
"""

AUTO_SKILL = """---
name: auto_route_skill
description: 自动路由技能 上传视频
invocation_mode: auto
triggers:
  - 上传视频
---

# SOP
1. 解析视频
"""


class TestInvocationModeRouting:
    def test_discovery_maps_user_to_auto_trigger_false(self):
        with tempfile.TemporaryDirectory(prefix="inv_user_") as tmp:
            d = Path(tmp) / "my_personal_process"
            d.mkdir()
            (d / "SKILL.md").write_text(USER_SKILL, encoding="utf-8")
            info = SKILLMD_parser.parse(d)
            assert info is not None
            assert info.auto_trigger_allowed is False

    def test_matcher_skips_user_mode(self):
        with tempfile.TemporaryDirectory(prefix="inv_match_") as tmp:
            u = Path(tmp) / "my_personal_process"
            a = Path(tmp) / "auto_route_skill"
            u.mkdir()
            a.mkdir()
            (u / "SKILL.md").write_text(USER_SKILL, encoding="utf-8")
            (a / "SKILL.md").write_text(AUTO_SKILL, encoding="utf-8")
            skills = [SKILLMD_parser.parse(u), SKILLMD_parser.parse(a)]
            skills = [s for s in skills if s]
            matched = SkillMatcher().match("请帮我上传视频 个人流程", skills)
            names = {s.name for s in matched}
            assert "auto_route_skill" in names
            assert "my_personal_process" not in names

    def test_candidates_skip_user_mode(self):
        skills = [
            {
                "skill_id": "my_personal_process",
                "name": "my_personal_process",
                "description": "个人流程技能",
                "scope": "workspace",
                "trigger_conditions": ["个人流程"],
                "invocation_mode": "user",
            },
            {
                "skill_id": "auto_route_skill",
                "name": "auto_route_skill",
                "description": "上传视频解析",
                "scope": "workspace",
                "trigger_conditions": ["上传视频"],
                "invocation_mode": "auto",
            },
        ]
        top = compute_skill_candidates(query_text="上传视频 个人流程", skills=skills, top_k=8)
        names = {c.name for c in top}
        assert "auto_route_skill" in names
        assert "my_personal_process" not in names

    def test_contract_user_forces_auto_trigger_false(self):
        contract, _ = build_contract_and_digest(
            name="x",
            version="1.0.0",
            kind="rule",
            input_schema={},
            output_schema={},
            metadata={"invocation_mode": "user", "permissions": ["llm:generate"]},
        )
        assert contract["auto_trigger_allowed"] is False


class TestSkillQualityLint:
    def test_misplaced_file_completion_warns(self):
        from core.management.skill_linter import lint_skill

        # Force registry reload so new skill_quality rules are discovered
        import core.management.skill_linter_base as lb

        lb._registry = None
        skill = {
            "name": "summarization",
            "description": "摘要",
            "metadata": {
                "completion_criterion": "1. 输出符合 ## FILE: 格式规范\n2. 每个文件包含完整可运行代码",
                "uses_file_output": False,
            },
        }
        report = lint_skill(skill)
        all_codes = set()
        for key in ("errors", "warnings", "infos", "issues"):
            for it in report.get(key) or []:
                if isinstance(it, dict):
                    all_codes.add(it.get("code"))
        assert "misplaced_file_completion" in all_codes

    def test_noop_phrases_warns(self):
        from core.management.skill_linter import lint_skill
        import core.management.skill_linter_base as lb

        lb._registry = None
        skill = {
            "name": "fluffy_skill",
            "description": "测试空话",
            "metadata": {
                "sop_goal": "生成高质量内容并遵循最佳实践",
                "body": "要彻底，正确处理错误和边界条件",
            },
        }
        report = lint_skill(skill)
        all_codes = {
            it.get("code")
            for key in ("errors", "warnings", "infos", "issues")
            for it in (report.get(key) or [])
            if isinstance(it, dict)
        }
        assert "skill_noop_phrases" in all_codes

    def test_invocation_mode_conflict_warns(self):
        from core.management.skill_linter import lint_skill
        import core.management.skill_linter_base as lb

        lb._registry = None
        skill = {
            "name": "conflict_skill",
            "description": "冲突模式",
            "metadata": {
                "invocation_mode": "user",
                "auto_trigger_allowed": True,
            },
        }
        report = lint_skill(skill)
        all_codes = {
            it.get("code")
            for key in ("errors", "warnings", "infos", "issues")
            for it in (report.get(key) or [])
            if isinstance(it, dict)
        }
        assert "invocation_mode_conflict" in all_codes
