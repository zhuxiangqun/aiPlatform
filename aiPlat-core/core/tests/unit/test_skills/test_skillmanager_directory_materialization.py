import os

import pytest


@pytest.mark.asyncio
async def test_skillmanager_create_skill_materializes_directory(tmp_path, monkeypatch):
    """
    Ensure SkillManager.create_skill creates:
    - skills/<skill_id>/SKILL.md
    - references/, scripts/, assets/ skeleton dirs
    and the skill can be discovered via SkillDiscovery.
    """
    base = tmp_path / "skills"
    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(base))

    from core.management.skill_manager import SkillManager
    from core.apps.skills.discovery import SkillDiscovery

    mgr = SkillManager(seed=False, scope="workspace")
    skill = await mgr.create_skill(
        name="TS Format",
        skill_type="frontend",
        description="格式化 TypeScript 文件并修复常见问题",
        input_schema={"file": {"type": "string", "required": True}},
        output_schema={"status": {"type": "string"}},
        metadata={"trigger_conditions": ["ts-format", "格式化 ts"]},
    )

    skill_id = skill.id
    skill_dir = base / skill_id
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "references").is_dir()
    assert (skill_dir / "scripts").is_dir()
    assert (skill_dir / "assets").is_dir()

    # discovery should find it
    discovery = SkillDiscovery(str(base))
    found = await discovery.discover()
    assert skill_id in found
    assert found[skill_id].name == skill_id
