import pytest


class DummyModel:
    async def generate(self, messages):
        # Return JSON payload with markdown (as requested)
        return type(
            "R",
            (),
            {
                "content": '{"report":{"summary":"ok","blocking":[],"non_blocking":[],"risk":"low"},"markdown":"# ok"}',
                "model": "dummy",
                "usage": {},
            },
        )


@pytest.mark.asyncio
async def test_generic_skill_parses_json_when_output_schema_present():
    from core.apps.skills.registry import _GenericSkill
    from core.harness.interfaces import SkillConfig, SkillContext

    skill = _GenericSkill(
        SkillConfig(
            name="code_review",
            description="x",
            output_schema={"report": {"type": "object"}, "markdown": {"type": "string"}},
            metadata={"sop_markdown": "SOP"},
        )
    )
    skill.set_model(DummyModel())
    res = await skill.execute(SkillContext(session_id="s", user_id="u"), {"diff_or_code": "print(1)"})
    assert res.success is True
    assert isinstance(res.output, dict)
    assert "report" in res.output and "markdown" in res.output

