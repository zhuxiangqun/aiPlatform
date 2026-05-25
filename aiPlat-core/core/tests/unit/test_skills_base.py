"""Tests for apps/skills/base.py — BaseSkill and skill types."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "aiPlat-core"))

import pytest


class TestSkillClassesExist:
    def test_text_generation_skill(self):
        from core.apps.skills.base import TextGenerationSkill
        from core.harness.interfaces import SkillConfig
        skill = TextGenerationSkill.__new__(TextGenerationSkill)
        assert skill is not None

    def test_code_generation_skill(self):
        from core.apps.skills.base import CodeGenerationSkill
        from core.harness.interfaces import SkillConfig
        skill = CodeGenerationSkill.__new__(CodeGenerationSkill)
        assert skill is not None

    def test_data_analysis_skill(self):
        from core.apps.skills.base import DataAnalysisSkill
        from core.harness.interfaces import SkillConfig
        skill = DataAnalysisSkill.__new__(DataAnalysisSkill)
        assert skill is not None

    def test_skill_factory_registry_exists(self):
        from core.apps.skills.base import _skill_factory_registry, register_skill_factory
        assert isinstance(_skill_factory_registry, dict)

    def test_register_and_resolve_factory(self):
        from core.apps.skills.base import register_skill_factory, _skill_factory_registry
        from core.apps.skills.base import TextGenerationSkill
        register_skill_factory("test_skill", TextGenerationSkill)
        assert "test_skill" in _skill_factory_registry
        assert _skill_factory_registry["test_skill"] == TextGenerationSkill
