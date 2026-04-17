import pytest


@pytest.mark.asyncio
async def test_skillmanager_loads_directory_skills_when_seed_false(tmp_path, monkeypatch):
    base = tmp_path / "skills"
    sd = base / "hello"
    sd.mkdir(parents=True)
    (sd / "SKILL.md").write_text(
        "---\nname: hello\n"
        "display_name: Hello\n"
        "description: test\n"
        "category: general\n"
        "version: 0.1.0\n"
        "status: enabled\n"
        "---\n\n# SOP\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AIPLAT_ENGINE_SKILLS_PATH", str(base))

    from core.management.skill_manager import SkillManager

    mgr = SkillManager(seed=False, scope="engine")
    skills = await mgr.list_skills()
    assert len(skills) == 1
    assert skills[0].id == "hello"
    assert skills[0].name == "Hello"
