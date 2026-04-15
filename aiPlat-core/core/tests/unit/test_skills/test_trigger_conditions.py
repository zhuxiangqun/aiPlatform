"""
trigger_conditions 功能测试

测试 Skill 的触发条件（路由表）功能
"""

import pytest
import tempfile
import os
from pathlib import Path
from core.apps.skills import (
    DiscoveredSkill,
    SKILLMD_parser,
)


class TestTriggerConditions:
    """trigger_conditions 功能测试"""
    
    def test_parse_trigger_conditions_from_yaml(self, tmp_path):
        """测试从 SKILL.md YAML 解析 trigger_conditions"""
        skill_dir = tmp_path / "test_skill"
        skill_dir.mkdir()
        
        skill_md_content = """---
name: test-skill
description: Test skill for trigger conditions
version: 1.0.0

trigger_conditions:
  - "帮我写"
  - "需要生成内容"
  - "撰写文案"

capabilities:
  - 文本生成

input_schema:
  prompt:
    type: string
    required: true
"""
        
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(skill_md_content)
        
        result = SKILLMD_parser.parse(skill_dir)
        
        assert result is not None
        assert result.trigger_conditions == ["帮我写", "需要生成内容", "撰写文案"]
    
    def test_parse_empty_trigger_conditions(self, tmp_path):
        """测试解析空的 trigger_conditions"""
        skill_dir = tmp_path / "empty_skill"
        skill_dir.mkdir()
        
        skill_md_content = """---
name: empty-skill
description: Test skill
version: 1.0.0

capabilities:
  - 文本生成
"""
        
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(skill_md_content)
        
        result = SKILLMD_parser.parse(skill_dir)
        
        assert result is not None
        assert result.trigger_conditions == []
    
    def test_discovered_skill_has_trigger_conditions_field(self):
        """测试 DiscoveredSkill 包含 trigger_conditions 字段"""
        skill = DiscoveredSkill(
            name="test-skill",
            display_name="Test Skill",
            description="Test description",
            trigger_conditions=["写文章", "生成文本"]
        )
        
        assert hasattr(skill, 'trigger_conditions')
        assert skill.trigger_conditions == ["写文章", "生成文本"]
    
    def test_trigger_conditions_default_is_empty_list(self):
        """测试 trigger_conditions 默认值为空列表"""
        skill = DiscoveredSkill(
            name="test-skill",
            display_name="Test Skill",
            description="Test description"
        )
        
        assert skill.trigger_conditions == []


class TestTriggerMatching:
    """trigger 匹配逻辑测试"""
    
    def test_keyword_matching(self):
        """测试关键词匹配"""
        conditions = ["帮我写", "需要生成内容", "撰写文案"]
        test_input = "请帮我写一篇文章"
        
        matched = any(condition.lower() in test_input.lower() for condition in conditions)
        assert matched is True
    
    def test_no_match(self):
        """测试不匹配"""
        conditions = ["帮我写", "需要生成内容"]
        test_input = "查询今天的天气"
        
        matched = any(condition.lower() in test_input.lower() for condition in conditions)
        assert matched is False
    
    def test_case_insensitive(self):
        """测试大小写不敏感"""
        conditions = ["帮我写", "需要生成内容"]
        test_input = "帮我写文章"
        
        matched = any(condition.lower() in test_input.lower() for condition in conditions)
        assert matched is True
    
    def test_empty_conditions_never_match(self):
        """测试空条件永远不匹配"""
        conditions = []
        test_input = "任何输入"
        
        matched = any(condition.lower() in test_input.lower() for condition in conditions)
        assert matched is False