import pytest


@pytest.mark.asyncio
async def test_skillmanager_bridge_sets_input_output_schema(tmp_path, monkeypatch):
    base = tmp_path / "skills"
    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(base))

    from core.management.skill_manager import SkillManager
    from core.apps.skills.registry import get_skill_registry

    mgr = SkillManager(seed=False, scope="workspace")
    skill = await mgr.create_skill(
        name="Schema Demo",
        skill_type="analysis",
        description="d",
        input_schema={"x": {"type": "string", "required": True}},
        output_schema={"y": {"type": "string"}},
    )

    inst = get_skill_registry().get(skill.id)
    assert inst is not None
    cfg = inst.get_config()
    assert isinstance(cfg.input_schema, dict) and "x" in cfg.input_schema
    assert isinstance(cfg.output_schema, dict) and "y" in cfg.output_schema

