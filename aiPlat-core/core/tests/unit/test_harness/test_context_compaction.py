import asyncio
import os

from core.harness.execution.loop import ReActLoop
from core.harness.interfaces.loop import LoopState, LoopConfig, LoopStateEnum


class _CompactionModel:
    """Minimal LLM stub — expose _config so sys_llm_generate can set temperature."""

    def __init__(self):
        self._config = type("Cfg", (), {"temperature": 0.2, "max_tokens": 256})()

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
    """Under token pressure, 5-level compaction runs without AttributeError.

    Contract (post 5-level path):
    - ContextCompression keeps ``_prev_summary`` / temperature fields
    - Model stub exposes ``_config`` for temperature writeback
    - Messages shrink (compaction_stats before → after) OR CONTEXT_SUMMARY appears
    - max_steps=1 may stop in REASONING (not FINISHED) — that is expected
    """
    monkeypatch.setenv("AIPLAT_ENABLE_CONTEXT_COMPACTION", "true")
    monkeypatch.setenv("AIPLAT_CONTEXT_COMPACTION_THRESHOLD", "0.5")
    monkeypatch.setenv("AIPLAT_CONTEXT_COMPACTION_PROTECT_LAST_N", "4")

    loop = ReActLoop(model=_CompactionModel(), tools=[])
    # Build a long message list
    msgs = [
        {
            "role": "user",
            "content": f"m{i} uuid=123e4567-e89b-12d3-a456-426614174000 a.py",
        }
        for i in range(12)
    ]
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

    # Must not crash; max_steps=1 often leaves REASONING with stop_reason=max_steps
    assert res.final_state is not None
    assert res.final_state.current in (
        LoopStateEnum.FINISHED,
        LoopStateEnum.REASONING,
        LoopStateEnum.ACTING,
        LoopStateEnum.OBSERVING,
    )

    out_msgs = res.final_state.context.get("messages")
    assert isinstance(out_msgs, list)
    assert len(out_msgs) < 12  # pressure reduced the transcript

    stats = res.final_state.metadata.get("compaction_stats") or {}
    has_summary = any(
        "CONTEXT_SUMMARY" in str(m.get("content", "")) for m in out_msgs if isinstance(m, dict)
    )
    shrunk = (
        isinstance(stats.get("before"), int)
        and isinstance(stats.get("after"), int)
        and stats["after"] < stats["before"]
    )
    assert has_summary or shrunk or res.final_state.metadata.get("compacted_messages") is True
    assert res.final_state.metadata.get("context_pressure") is True
