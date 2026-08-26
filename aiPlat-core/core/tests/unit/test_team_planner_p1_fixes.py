"""
P1 回归测试（core 侧）— P1-5 team_planner 模型用途推断配置化（2026-08-25）。

覆盖:
- P1-5: team_planner 用技能名关键词推断模型用途（:273-280 的 architecture/design/code/
  generation/test 匹配）违反 CLAUDE.md §5.29/v4.1（core 层禁止按名称关键词推断能力类型）
  → 改为配置驱动解析链：team YAML 显式 → AGENT.md frontmatter → SKILL.md frontmatter
  `skill_model_purpose` → 默认 "chat"。

运行方式（仓库根）：
    TMPDIR=$(pwd)/../.tmp_pytest AIPLAT_HOME=$(pwd)/../.tmp_pytest/home \
        python3 -m pytest aiPlat-core/core/tests/unit/test_team_planner_p1_fixes.py -v
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

CORE_ROOT = Path(__file__).resolve().parents[3]
PLANNER_PATH = CORE_ROOT / "core" / "harness" / "execution" / "team_planner.py"

import sys
sys.path.insert(0, str(CORE_ROOT))

from core.harness.execution.team_planner import _enrich_stage_from_agent


class TestP1_5ConfigDrivenModelPurpose:
    """模型用途必须配置驱动，禁止技能名关键词推断。"""

    def test_no_keyword_inference_in_planner(self):
        """静态证据：team_planner 不再含 skill-name 关键词推断。"""
        src = PLANNER_PATH.read_text(encoding="utf-8")
        assert '"architecture" in _skill' not in src, "P1-5 未修复：仍按技能名推断"
        assert '"generation" in _skill' not in src, "P1-5 未修复：仍按技能名推断"
        assert "skill_model_purpose" in src
        assert "_load_skill_frontmatter" in src, "P1-5 未修复：缺 SKILL.md frontmatter 读取"

    def _enrich(self, agent_id: str, skill_name: str):
        """mock AGENT.md 无声明 → 走 SKILL.md frontmatter。"""
        with patch(
            "core.api.facades.agent_facade.get_agent_frontmatter",
            return_value={"agent_type": "react"},
        ):
            return _enrich_stage_from_agent(
                {"agent_id": agent_id, "skill_name": skill_name})

    def test_skill_frontmatter_drives_purpose(self):
        """行为证据：engine SKILL.md 声明的 skill_model_purpose 生效（行为保持）。"""
        stage = self._enrich("architect_agent", "architecture_design")
        assert stage["skill_model_purpose"] == "reasoning", stage
        stage = self._enrich("agent_engineer", "code_generation")
        assert stage["skill_model_purpose"] == "code_gen", stage
        stage = self._enrich("frontend_developer", "app_page_generation")
        assert stage["skill_model_purpose"] == "code_gen", stage

    def test_unknown_skill_defaults_chat(self):
        """无声明 skill → 默认 chat（与旧关键词推断的 else 分支一致）。"""
        stage = self._enrich("pm_agent", "requirement_analysis")
        assert stage["skill_model_purpose"] == "chat", stage

    def test_agent_frontmatter_overrides_skill(self):
        """AGENT.md frontmatter 显式声明优先于 SKILL.md。"""
        with patch(
            "core.api.facades.agent_facade.get_agent_frontmatter",
            return_value={"agent_type": "react", "skill_model_purpose": "reasoning"},
        ):
            stage = _enrich_stage_from_agent(
                {"agent_id": "custom", "skill_name": "code_generation"})
        assert stage["skill_model_purpose"] == "reasoning", stage
