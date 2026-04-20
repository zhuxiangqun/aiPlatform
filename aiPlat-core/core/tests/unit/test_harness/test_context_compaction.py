import asyncio
import os

from core.harness.execution.loop import ReActLoop
from core.harness.interfaces.loop import LoopState, LoopConfig, LoopStateEnum


class _CompactionModel:
    async def generate(self, prompt):
        class _R:
            def __init__(self, content, usage=None):
                self.content = content
                self.usage = usage or {"total_tokens": 5}

        # If called for summary
        if isinstance(prompt, str) and "你是一个对话压缩器" in prompt:
            return _R("SUMMARY_OK uuid=123e4567-e89b-12d3-a456-426614174000 file=a.py")

        # Normal reasoning: finish immediately
        return _R("DONE: ok")


def test_context_compaction_inserts_summary(monkeypatch):
    monkeypatch.setenv("AIPLAT_ENABLE_CONTEXT_COMPACTION", "true")
    monkeypatch.setenv("AIPLAT_CONTEXT_COMPACTION_THRESHOLD", "0.5")
    monkeypatch.setenv("AIPLAT_CONTEXT_COMPACTION_PROTECT_LAST_N", "4")

    loop = ReActLoop(model=_CompactionModel(), tools=[])
    # Build a long message list
    msgs = [{"role": "user", "content": f"m{i} uuid=123e4567-e89b-12d3-a456-426614174000 a.py"} for i in range(12)]
    state = LoopState(
        context={
            "task": "t",
            "messages": msgs,
            "session_id": "s",
            "user_id": "u",
        }
    )
    # Simulate budget pressure
    state.used_tokens = 100
    res = asyncio.run(loop.run(state, LoopConfig(max_steps=1, max_tokens=100)))
    assert res.final_state.current == LoopStateEnum.FINISHED
    out_msgs = res.final_state.context.get("messages")
    assert isinstance(out_msgs, list)
    assert out_msgs[0]["role"] == "system"
    assert "CONTEXT_SUMMARY" in out_msgs[0]["content"]
    assert res.final_state.metadata.get("compacted_messages") is True

