"""
Skill Evolution 功能测试

测试 Skill 进化机制（CAPTURED/FIX/DERIVED）
"""

import pytest
from datetime import datetime
from core.apps.skills.evolution.types import (
    EvolutionType,
    TriggerType,
    TriggerStatus,
    EvolutionTrigger,
    SkillVersion,
)


class TestEvolutionType:
    """Evolution type 测试"""
    
    def test_evolution_type_enum_values(self):
        """测试进化类型枚举值"""
        assert EvolutionType.FIX.value == "fix"
        assert EvolutionType.DERIVED.value == "derived"
        assert EvolutionType.CAPTURED.value == "captured"
    
    def test_evolution_type_from_string(self):
        """测试从字符串创建类型"""
        etype = EvolutionType("fix")
        assert etype == EvolutionType.FIX
        
        etype = EvolutionType("captured")
        assert etype == EvolutionType.CAPTURED


class TestTriggerType:
    """触发类型测试"""
    
    def test_trigger_type_enum_values(self):
        """测试触发类型枚举值"""
        assert TriggerType.POST_EXEC.value == "post_exec"
        assert TriggerType.TOOL_DEGRADATION.value == "tool_degradation"
        assert TriggerType.METRIC.value == "metric"


class TestTriggerStatus:
    """触发状态测试"""
    
    def test_trigger_status_enum_values(self):
        """测试触发状态枚举值"""
        assert TriggerStatus.PENDING.value == "pending"
        assert TriggerStatus.RUNNING.value == "running"
        assert TriggerStatus.COMPLETED.value == "completed"
        assert TriggerStatus.FAILED.value == "failed"


class TestEvolutionTrigger:
    """进化触发记录测试"""
    
    def test_create_evolution_trigger(self):
        """测试创建触发记录"""
        trigger = EvolutionTrigger(
            id="trigger-001",
            skill_id="skill-001",
            trigger_type=TriggerType.POST_EXEC,
            suggestion="Improve output quality"
        )
        
        assert trigger.id == "trigger-001"
        assert trigger.skill_id == "skill-001"
        assert trigger.trigger_type == TriggerType.POST_EXEC
    
    def test_trigger_default_status(self):
        """测试默认状态"""
        trigger = EvolutionTrigger(
            id="trigger-001",
            skill_id="skill-001",
            trigger_type=TriggerType.POST_EXEC
        )
        
        assert trigger.status == TriggerStatus.PENDING


class TestSkillVersion:
    """Skill 版本测试"""
    
    def test_create_skill_version(self):
        """测试创建版本"""
        version = SkillVersion(
            id="v1.0.0",
            skill_id="skill-001",
            version="1.0.0"
        )
        
        assert version.id == "v1.0.0"
        assert version.skill_id == "skill-001"
        assert version.version == "1.0.0"
    
    def test_version_with_lineage(self):
        """测试带血缘的版本"""
        version = SkillVersion(
            id="v1.1.0",
            skill_id="skill-001",
            version="1.1.0",
            parent_version="1.0.0",
            evolution_type=EvolutionType.FIX
        )
        
        assert version.parent_version == "1.0.0"
        assert version.evolution_type == EvolutionType.FIX


class TestEvolutionMetadata:
    """测试进化元数据"""
    
    def test_create_evolution_metadata(self):
        """测试创建进化元数据"""
        evolution = {
            "status": "stable",
            "last_evolution": "2026-04-14T10:00:00Z",
            "evolution_count": 3,
            "parent_skill_id": None,
            "child_skill_ids": ["skill-002"]
        }
        
        assert evolution["status"] == "stable"
        assert evolution["last_evolution"] == "2026-04-14T10:00:00Z"
        assert evolution["evolution_count"] == 3
        assert len(evolution["child_skill_ids"]) == 1
    
    def test_evolution_status_transitions(self):
        """测试有效的状态转换"""
        valid_transitions = {
            "stable": ["captured", "fix"],
            "captured": ["stable", "derived", "fix"],
            "fix": ["stable", "derived"],
            "derived": ["stable"]
        }
        
        assert "captured" in valid_transitions["stable"]
        assert "derived" in valid_transitions["captured"]
        assert "stable" in valid_transitions["fix"]