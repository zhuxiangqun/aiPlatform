import pytest
from unittest.mock import AsyncMock
from dataclasses import dataclass
from types import SimpleNamespace

from core.harness.execution.tool_calling import parse_tool_call, parse_action_call
from core.harness.execution.loop import ReActLoop
from core.harness.interfaces.loop import LoopState, LoopConfig, LoopStateEnum


def test_parse_tool_call_structured_json():
    text = """```json
{"tool":"search","args":{"q":"x"}}
```"""
    parsed = parse_tool_call(text)
    assert parsed is not None
    assert parsed.tool_name == "search"
    assert parsed.tool_args == {"q": "x"}
    assert parsed.format == "json"


def test_parse_tool_call_openai_style():
    text = '{"name":"search","arguments":"{\\"q\\":\\"x\\"}"}'
    parsed = parse_tool_call(text)
    assert parsed is not None
    assert parsed.tool_name == "search"
    assert parsed.tool_args == {"q": "x"}


def test_parse_tool_call_action_fallback():
    text = 'ACTION: search: {\"q\":\"x\"}'
    parsed = parse_tool_call(text)
    assert parsed is not None
    assert parsed.tool_name == "search"
    assert parsed.tool_args == {"q": "x"}
    assert parsed.format == "action"


def test_parse_action_call_skill_structured():
    text = '{"skill":"summarize","args":{"text":"x"}}'
    parsed = parse_action_call(text)
    assert parsed is not None
    assert parsed.kind == "skill"
    assert parsed.name == "summarize"
    assert parsed.args == {"text": "x"}


@dataclass
class _SkillResult:
    output: object = None


class _EchoSkill:
    name = "echo_skill"

    def __init__(self):
        self.last_args = None

    async def execute(self, context, args):
        self.last_args = args
        return _SkillResult(output=args)


@dataclass
class _ToolResult:
    success: bool = True
    output: object = None
    error: str | None = None


class _EchoTool:
    name = "echo"
    description = "echo tool"

    def __init__(self):
        self.last_args = None

    async def execute(self, args):
        self.last_args = args
        return _ToolResult(success=True, output=args)


@pytest.mark.asyncio
async def test_react_loop_executes_structured_tool_call():
    tool = _EchoTool()
    model = SimpleNamespace()
    model.generate = AsyncMock(return_value=SimpleNamespace(content="{\"tool\":\"echo\",\"args\":{\"a\":1}}"))

    loop = ReActLoop(model=model, tools=[tool], config=LoopConfig(max_steps=1))
    state = LoopState(current=LoopStateEnum.INIT, context={"task": "x", "messages": []})

    # only run one step
    result = await loop.run(state, LoopConfig(max_steps=1))
    assert result is not None
    assert result.final_state.context.get("tool_call", {}).get("tool") == "echo"
    assert tool.last_args == {"a": 1}


@pytest.mark.asyncio
async def test_react_loop_does_not_trigger_skill_by_substring():
    # reasoning contains skill name, but no SKILL/json marker => should not execute
    skill = _EchoSkill()
    model = SimpleNamespace()
    model.generate = AsyncMock(return_value=SimpleNamespace(content="I will use echo_skill to do it."))
    loop = ReActLoop(model=model, tools=[], skills=[skill], config=LoopConfig(max_steps=1))
    state = LoopState(current=LoopStateEnum.INIT, context={"task": "x", "messages": []})
    res = await loop.run(state, LoopConfig(max_steps=1))
    assert res is not None
    assert skill.last_args is None


@pytest.mark.asyncio
async def test_react_loop_executes_explicit_skill_call():
    skill = _EchoSkill()
    model = SimpleNamespace()
    model.generate = AsyncMock(return_value=SimpleNamespace(content='{"skill":"echo_skill","args":{"a":1}}'))
    loop = ReActLoop(model=model, tools=[], skills=[skill], config=LoopConfig(max_steps=1))
    state = LoopState(current=LoopStateEnum.INIT, context={"task": "x", "messages": []})
    res = await loop.run(state, LoopConfig(max_steps=1))
    assert res is not None
    assert skill.last_args == {"a": 1}
