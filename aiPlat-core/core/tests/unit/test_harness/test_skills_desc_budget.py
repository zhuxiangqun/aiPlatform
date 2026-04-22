from dataclasses import dataclass


def test_skills_desc_budget_truncates_and_hides(monkeypatch):
    # ensure we have a couple of skills in registry
    from core.apps.skills.registry import _GenericSkill
    from core.harness.interfaces import SkillConfig
    from core.apps.skills import get_skill_registry
    from core.harness.execution.loop import ReActLoop

    reg = get_skill_registry()
    # Ensure a deterministic first entry (sorted by name) that will be truncated.
    reg.register(_GenericSkill(SkillConfig(name="a-long-skill", description="x" * 200, metadata={"skill_kind": "rule"})))
    reg.register(_GenericSkill(SkillConfig(name="b-long-skill", description="y" * 200, metadata={"skill_kind": "rule"})))

    monkeypatch.setenv("AIPLAT_SKILL_DESC_PER_SKILL_MAX_CHARS", "30")
    monkeypatch.setenv("AIPLAT_SKILLS_DESC_MAX_CHARS", "60")

    loop = ReActLoop()
    text, stats = loop._build_skills_desc()  # type: ignore[attr-defined]
    assert isinstance(text, str)
    assert "…(truncated)" in text
    assert "use skill_find" in text
    assert stats["skills_truncated"] >= 1
