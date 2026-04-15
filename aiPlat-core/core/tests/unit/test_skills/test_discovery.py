import pytest
import tempfile
import os
from pathlib import Path
from core.apps.skills import (
    SkillDiscovery,
    SkillLoader,
    DiscoveredSkill,
    SKILLMD_parser,
    SkillMetadata,
    BaseSkill,
)
from core.harness.interfaces import SkillConfig, SkillContext, SkillResult


class TestSkillMetadata:
    """Test SkillMetadata with extended fields"""
    
    def test_basic_fields(self):
        meta = SkillMetadata(
            name="test_skill",
            description="Test skill description"
        )
        assert meta.name == "test_skill"
        assert meta.description == "Test skill description"
        assert meta.version == "1.0.0"
        assert meta.category == "general"
    
    def test_extended_fields(self):
        meta = SkillMetadata(
            name="test_skill",
            description="Test skill description",
            display_name="Test Skill Display",
            capabilities=["cap1", "cap2"],
            examples=[{"input": "test", "output": "result"}],
            requirements=[{"name": "openai", "version": ">=1.0.0"}],
            permissions=["network_access"]
        )
        assert meta.display_name == "Test Skill Display"
        assert meta.capabilities == ["cap1", "cap2"]
        assert meta.examples == [{"input": "test", "output": "result"}]
        assert meta.requirements == [{"name": "openai", "version": ">=1.0.0"}]
        assert meta.permissions == ["network_access"]
    
    def test_display_name_default(self):
        meta = SkillMetadata(
            name="test_skill",
            description="Test"
        )
        assert meta.display_name == "test_skill"


class TestSKILLMDParser:
    """Test SKILL.md parser"""
    
    def test_parse_front_matter(self, tmp_path):
        skill_dir = tmp_path / "text_generation"
        skill_dir.mkdir()
        
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: text_generation
display_name: Text Generation
description: Generate text based on prompt
version: 1.0.0
category: generation
tags: [text, gpt]
capabilities:
  - Generate marketing copy
  - Write emails
input_schema:
  prompt:
    type: string
    required: true
output_schema:
  text:
    type: string
---
""")
        
        parser = SKILLMD_parser()
        result = parser.parse(skill_dir)
        
        assert result is not None
        assert result.name == "text_generation"
        assert result.display_name == "Text Generation"
        assert result.category == "generation"
        assert result.capabilities == ["Generate marketing copy", "Write emails"]
    
    def test_parse_no_file(self, tmp_path):
        skill_dir = tmp_path / "empty"
        skill_dir.mkdir()
        
        parser = SKILLMD_parser()
        result = parser.parse(skill_dir)
        
        assert result is None
    
    def test_parse_empty_dir(self):
        parser = SKILLMD_parser()
        result = parser.parse(Path("/nonexistent"))
        assert result is None


class TestSkillDiscovery:
    """Test skill discovery system"""
    
    @pytest.mark.asyncio
    async def test_discover_empty_dir(self, tmp_path):
        discovery = SkillDiscovery(str(tmp_path))
        result = await discovery.discover()
        assert result == {}
    
    @pytest.mark.asyncio
    async def test_discover_with_skills(self, tmp_path):
        skill_dir = tmp_path / "text_generation"
        skill_dir.mkdir()
        
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: text_generation
display_name: Text Generation
description: Generate text based on prompt
version: 1.0.0
category: generation
tags: [text]
capabilities:
  - Generate text
permissions:
  - network_access
---
""")
        
        discovery = SkillDiscovery(str(tmp_path))
        result = await discovery.discover()
        
        assert "text_generation" in result
        skill_info = result["text_generation"]
        assert skill_info.name == "text_generation"
        assert skill_info.category == "generation"
        assert skill_info.capabilities == ["Generate text"]
    
    @pytest.mark.asyncio
    async def test_list_by_category(self, tmp_path):
        (tmp_path / "skill1").mkdir()
        (tmp_path / "skill1").joinpath("SKILL.md").write_text("""---
name: skill1
category: generation
---
""")
        
        (tmp_path / "skill2").mkdir()
        (tmp_path / "skill2").joinpath("SKILL.md").write_text("""---
name: skill2
category: analysis
---
""")
        
        discovery = SkillDiscovery(str(tmp_path))
        await discovery.discover()
        
        gen_skills = discovery.list_by_category("generation")
        assert len(gen_skills) == 1
        assert gen_skills[0].name == "skill1"


class TestSkillLoader:
    """Test skill loader with caching"""
    
    @pytest.mark.asyncio
    async def test_load_reference_on_demand(self, tmp_path):
        skill_dir = tmp_path / "text_generation"
        skill_dir.mkdir()
        
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: text_generation
---
""")
        
        ref_dir = skill_dir / "references"
        ref_dir.mkdir()
        ref_dir.joinpath("guide.md").write_text("# Guide\n\nThis is a guide.")
        
        discovery = SkillDiscovery(str(tmp_path))
        await discovery.discover()
        
        loader = SkillLoader(discovery)
        
        refs = loader.list_references("text_generation")
        assert "guide.md" in refs
        
        content = loader.load_reference("text_generation", "guide.md")
        assert content == "# Guide\n\nThis is a guide."
    
    @pytest.mark.asyncio
    async def test_load_script(self, tmp_path):
        skill_dir = tmp_path / "text_generation"
        skill_dir.mkdir()
        
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: text_generation
---
""")
        
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()
        scripts_dir.joinpath("preprocess.sh").write_text("echo 'preprocess'")
        
        discovery = SkillDiscovery(str(tmp_path))
        await discovery.discover()
        
        loader = SkillLoader(discovery)
        
        scripts = loader.list_scripts("text_generation")
        assert "preprocess.sh" in scripts
        
        content = loader.load_script("text_generation", "preprocess.sh")
        assert content == "echo 'preprocess'"