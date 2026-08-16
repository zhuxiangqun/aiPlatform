from dataclasses import dataclass


def test_skills_desc_budget_truncates_and_hides(monkeypatch):
    # ensure we have a couple of skills in registry
    from core.apps.skills.registry import _GenericSkill
    from core.harness.interfaces import SkillConfig
    from core.apps.skills import get_skill_registry
    from core.harness.execution.loop import ReActLoop

    reg = get_skill_registry()
    # Ensure a deterministic first entry (sorted by name) that will be truncated.
    # §5.19: every registered skill must declare effects (read-only here).
    s1 = _GenericSkill(SkillConfig(name="a-long-skill", description="x" * 200, metadata={"skill_kind": "rule"}, effects=[{"type": "read", "resources": [], "idempotent": True}]))
    s2 = _GenericSkill(SkillConfig(name="b-long-skill", description="y" * 200, metadata={"skill_kind": "rule"}, effects=[{"type": "read", "resources": [], "idempotent": True}]))
    reg.register(s1)
    reg.register(s2)

    monkeypatch.setenv("AIPLAT_SKILL_DESC_PER_SKILL_MAX_CHARS", "30")
    monkeypatch.setenv("AIPLAT_SKILLS_DESC_MAX_CHARS", "60")

    loop = ReActLoop(skills=[s1, s2])
    text, stats = loop._build_skills_desc()  # type: ignore[attr-defined]
    assert isinstance(text, str)
    assert "…(truncated)" in text
    assert "use skill_find" in text
    assert stats["skills_truncated"] >= 1
