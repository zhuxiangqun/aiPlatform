"""output_schema payload keys must skip UI meta (x-display-profile)."""
import pytest

from core.apps.skills.registry import _output_schema_payload_keys, _GenericSkill
from core.harness.interfaces import SkillConfig, SkillContext


def test_payload_keys_prefer_properties_over_display_profile():
    schema = {
        "x-display-profile": "architecture",
        "type": "object",
        "required": True,
        "description": "架构 JSON",
        "properties": {
            "title": {"type": "string"},
            "context": {"type": "string"},
            "components": {"type": "array"},
        },
    }
    keys = _output_schema_payload_keys(schema)
    assert keys == ["title", "context", "components"]
    assert "x-display-profile" not in keys
    assert "type" not in keys


def test_payload_keys_flat_schema_skips_meta():
    schema = {
        "x-display-profile": "prd",
        "report": {"type": "object"},
        "markdown": {"type": "string"},
    }
    keys = _output_schema_payload_keys(schema)
    assert keys == ["report", "markdown"]


@pytest.mark.asyncio
async def test_unparsed_output_wraps_as_text_not_display_profile():
    class DummyModel:
        async def generate(self, messages):
            return type(
                "R",
                (),
                {
                    "content": "### 步骤1：分析\n使用内部钉钉 SDK",
                    "model": "dummy",
                    "usage": {},
                },
            )

    skill = _GenericSkill(
        SkillConfig(
            name="architecture_design",
            description="x",
            output_schema={
                "x-display-profile": "architecture",
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "context": {"type": "string"},
                },
            },
            metadata={
                "sop_markdown": "输出 JSON",
                "execution_type": "prompt",
                "output_schema": {
                    "x-display-profile": "architecture",
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "context": {"type": "string"},
                    },
                },
            },
        )
    )
    skill.set_model(DummyModel())

    import core.harness.syscalls.llm as llm_mod

    async def fake_gen(model, messages, **kwargs):
        return await DummyModel().generate(messages)

    original = llm_mod.sys_llm_generate
    llm_mod.sys_llm_generate = fake_gen
    try:
        res = await skill.execute(
            SkillContext(session_id="s", user_id="u"),
            {"message": "设计架构"},
        )
    finally:
        llm_mod.sys_llm_generate = original

    assert res.success is True
    assert isinstance(res.output, dict)
    assert "x-display-profile" not in res.output
    assert "text" in res.output
    assert "步骤1" in str(res.output["text"])
    assert (res.metadata or {}).get("parsed_json") is False


@pytest.mark.asyncio
async def test_architecture_lone_api_rejected_not_delivered():
    """Fail-constraint bait: single endpoint must not finalize as architecture."""
    class DummyModel:
        async def generate(self, messages):
            return type(
                "R",
                (),
                {
                    "content": (
                        '{"method":"POST","path":"/api/tickets",'
                        '"request":{"body":{"a":1}},'
                        '"response":{"status":201,"body":{"id":"1"}}}'
                    ),
                    "model": "dummy",
                    "usage": {},
                },
            )

    skill = _GenericSkill(
        SkillConfig(
            name="architecture_design",
            description="x",
            output_schema={
                "x-display-profile": "architecture",
                "type": "object",
                "properties": {"title": {"type": "string"}},
            },
            metadata={
                "sop_markdown": "JSON",
                "execution_type": "prompt",
                "output_schema": {
                    "x-display-profile": "architecture",
                    "properties": {"title": {"type": "string"}},
                },
            },
        )
    )
    skill.set_model(DummyModel())
    import core.harness.syscalls.llm as llm_mod

    calls = {"n": 0}

    async def fake_gen(model, messages, **kwargs):
        calls["n"] += 1
        return await DummyModel().generate(messages)

    original = llm_mod.sys_llm_generate
    llm_mod.sys_llm_generate = fake_gen
    try:
        res = await skill.execute(
            SkillContext(session_id="s", user_id="u"), {"message": "x"}
        )
    finally:
        llm_mod.sys_llm_generate = original

    assert res.success is False
    assert "lone_api" in str(res.error or "")
    assert (res.metadata or {}).get("lone_api_rejected") is True
    # First shot + one in-skill retry, then still reject.
    assert calls["n"] == 2
    assert (res.metadata or {}).get("lone_api_retry_attempted") is True


@pytest.mark.asyncio
async def test_architecture_lone_api_in_skill_retry_succeeds():
    """Lone API on first shot → in-skill retry returns full architecture."""
    lone = (
        '{"method":"POST","path":"/api/tickets",'
        '"request":{"body":{"a":1}},'
        '"response":{"status":201,"body":{"id":"1"}}}'
    )
    full = (
        '{"title":"t","context":"c","components":[{"name":"n"}],'
        '"data_flow":"d","api_contracts":['
        '{"method":"POST","path":"/a","request":{},"response":{}},'
        '{"method":"GET","path":"/b","request":{},"response":{}},'
        '{"method":"GET","path":"/c","request":{},"response":{}}'
        '],"security":"s","rollout_and_risks":"r"}'
    )

    skill = _GenericSkill(
        SkillConfig(
            name="architecture_design",
            description="x",
            output_schema={
                "x-display-profile": "architecture",
                "type": "object",
                "properties": {"title": {"type": "string"}},
            },
            metadata={
                "sop_markdown": "JSON",
                "execution_type": "prompt",
                "output_schema": {
                    "x-display-profile": "architecture",
                    "properties": {"title": {"type": "string"}},
                },
            },
        )
    )
    skill.set_model(object())
    import core.harness.syscalls.llm as llm_mod

    calls = {"n": 0}

    async def fake_gen(model, messages, **kwargs):
        calls["n"] += 1
        content = lone if calls["n"] == 1 else full
        return type("R", (), {"content": content, "model": "dummy", "usage": {}})()

    original = llm_mod.sys_llm_generate
    llm_mod.sys_llm_generate = fake_gen
    try:
        res = await skill.execute(
            SkillContext(session_id="s", user_id="u"), {"message": "x"}
        )
    finally:
        llm_mod.sys_llm_generate = original

    assert res.success is True
    assert calls["n"] == 2
    assert (res.metadata or {}).get("lone_api_retried") is True
    assert isinstance(res.output, dict) and res.output.get("title") == "t"
