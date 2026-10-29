import asyncio

from core.apps.tools.permission import get_permission_manager
from core.harness.execution.loop import ReActLoop
from core.harness.interfaces.loop import LoopState, LoopConfig, LoopStateEnum
from core.harness.interfaces.types import Permission


class _AlwaysFailModel:
    _config = type("_Cfg", (), {"temperature": 0.0})()

    def __init__(self):
        self._i = 0

    async def generate(self, messages):
        class _R:
            def __init__(self, c):
                self.content = c

        # Always call the same tool
        self._i += 1
        return _R('ACTION: FAILTOOL: {"input":"x"}')


class _FailTool:
    name = "failtool"

    async def execute(self, params):
        raise RuntimeError("boom")


def test_observability_control_pauses_on_high_tool_error_rate():
    # PolicyGate requires EXECUTE before tools can fail and accumulate error rate.
    pm = get_permission_manager()
    pm.grant_permission("u", "failtool", Permission.EXECUTE)
    pm.grant_permission("u", "FAILTOOL", Permission.EXECUTE)

    loop = ReActLoop(model=_AlwaysFailModel(), tools=[_FailTool()])
    state = LoopState(
        context={
            "task": "t",
            "messages": [{"role": "user", "content": "t"}],
            "session_id": "s",
            "user_id": "u",
        }
    )
    res = asyncio.run(loop.run(state, LoopConfig(max_steps=20)))
    assert res.final_state.current in (LoopStateEnum.PAUSED, LoopStateEnum.ERROR)
    assert res.final_state.metadata.get("control_action") == "require_manual"
    assert res.final_state.metadata.get("tool_calls") >= 10
