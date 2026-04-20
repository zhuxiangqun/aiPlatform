import pytest


@pytest.mark.asyncio
async def test_create_skill_injects_sop_into_registry_config(tmp_path, monkeypatch):
    base = tmp_path / "skills"
    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(base))

    from core.management.skill_manager import SkillManager
    from core.apps.skills.registry import get_skill_registry

    mgr = SkillManager(seed=False, scope="workspace")
    skill = await mgr.create_skill(
        name="SOP Demo",
        skill_type="general",
        description="用于验证 SOP 注入",
        input_schema={},
        output_schema={},
        metadata={"capabilities": ["tool:webfetch", "tool:websearch"]},
    )

    inst = get_skill_registry().get(skill.id)
    assert inst is not None
    cfg = inst.get_config()
    sop = (cfg.metadata or {}).get("sop_markdown", "")
    assert isinstance(sop, str)
    # from create_skill template body
    assert "工作流程" in sop

    caps = (cfg.metadata or {}).get("capabilities")
    assert caps == ["tool:webfetch", "tool:websearch"]
