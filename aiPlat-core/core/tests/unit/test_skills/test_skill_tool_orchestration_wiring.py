import pytest


@pytest.mark.asyncio
async def test_generic_skill_prefers_react_agent_when_tools_present(tmp_path, monkeypatch):
    """
    Smoke test: when SkillContext.tools is non-empty, _GenericSkill.execute should take
    the tool-orchestration path (ReAct agent). We don't require a real model here; we just
    assert it fails with "No LLM adapter" before attempting orchestration.
    """
    from core.apps.skills.registry import _GenericSkill
    from core.harness.interfaces import SkillConfig, SkillContext

    skill = _GenericSkill(SkillConfig(name="x", description="y", metadata={"sop_markdown": "SOP"}))
    # no model configured -> should return error
    res = await skill.execute(SkillContext(session_id="s", user_id="u", tools=["bash"]), {"prompt": "hi"})
    assert res.success is False
    assert "No LLM adapter configured" in (res.error or "")

