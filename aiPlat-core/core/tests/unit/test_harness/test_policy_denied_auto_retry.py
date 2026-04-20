import asyncio


class _DummyModel:
    async def generate(self, prompt):
        class _R:
            def __init__(self, content):
                self.content = content
                self.usage = {"total_tokens": 1}

        # Always try to call the tool
        return _R('{"tool":"denytool","args":{}}')


class _DummyTool:
    name = "denytool"
    description = "x"


def test_policy_denied_auto_retry(monkeypatch):
    # Ensure auto-retry is enabled
    monkeypatch.setenv("AIPLAT_POLICY_DENIED_AUTO_RETRY", "true")
    monkeypatch.setenv("AIPLAT_POLICY_DENIED_MAX_AUTO_RETRY", "3")

    from core.harness.execution.loop import ReActLoop
    from core.harness.interfaces.loop import LoopState, LoopConfig, LoopStateEnum

    async def _fake_sys_tool_call(tool, args, **kwargs):
        class _R:
            success = False
            error = "policy_denied"
            output = None
            metadata = {"reason": "denied_for_test", "approval_request_id": "apr-1"}

        return _R()

    # Patch syscall
    import core.harness.execution.loop as loopmod

    monkeypatch.setattr(loopmod, "sys_tool_call", _fake_sys_tool_call)

    loop = ReActLoop(model=_DummyModel(), tools=[_DummyTool()])
    state = LoopState(context={"task": "t", "messages": [], "session_id": "s", "user_id": "u"})
    res = asyncio.run(loop.run(state, LoopConfig(max_steps=2, max_tokens=100)))
    # Should not be paused on first policy_denied (auto-retry provides guidance)
    assert res.final_state.current != LoopStateEnum.PAUSED
    assert res.final_state.metadata.get("pause_requested") is not True
