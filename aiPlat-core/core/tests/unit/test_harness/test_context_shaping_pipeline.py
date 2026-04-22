import anyio


def test_context_shaping_pipeline_attaches_stats(monkeypatch):
    monkeypatch.setenv("AIPLAT_ENABLE_CONTEXT_SHAPING_PIPELINE", "true")
    monkeypatch.setenv("AIPLAT_ENABLE_CONTEXT_COMPACTION", "false")  # avoid LLM calls

    from core.harness.execution.loop import ReActLoop
    from core.harness.interfaces.loop import LoopState

    loop = ReActLoop(model=None)
    state = LoopState()
    state.context["messages"] = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]

    anyio.run(loop._apply_context_shaping_pipeline, state)  # type: ignore[attr-defined]
    assert "context_shaping_stats" in state.context
    stats = state.context["context_shaping_stats"]
    assert isinstance(stats, dict)
    assert stats.get("enabled") is True
    assert isinstance(stats.get("stages"), list)
    assert len(stats.get("stages")) >= 3

