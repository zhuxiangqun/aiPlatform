import pytest

from core.harness.execution.loop import ReActLoop
from core.harness.interfaces.loop import LoopConfig, LoopState, LoopStateEnum
from core.adapters.llm.mock_adapter import MockAdapter


@pytest.mark.anyio
async def test_react_loop_can_finish_on_done_reasoning():
    loop = ReActLoop(model=MockAdapter())
    state = LoopState()
    state.context["task"] = "say hello"
    state.context["messages"] = [{"role": "user", "content": "hello"}]

    result = await loop.run(state, LoopConfig(max_steps=3))
    assert result.success is True
    assert result.final_state.current == LoopStateEnum.FINISHED
    assert isinstance(result.output, (str, type(None)))

