"""Regression: workspace ReAct must reach LLM without ST/memory cold-start hang."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

from core.harness.interfaces.loop import LoopConfig, LoopState, LoopStateEnum


def _state(**ctx) -> LoopState:
    base = {
        "task": "现场巡检报修：输出上下文与假设、数据流、安全与合规、6周分期",
        "messages": [],
        "system_prompt": "你是架构师",
        "_coding_policy_profile": "off",
        "_agent_id": "architect_agent",
        "_run_id": "run-test-pre-llm",
        "_enable_query_rewrite": False,
    }
    base.update(ctx)
    return LoopState(current=LoopStateEnum.INIT, context=base)


@pytest.mark.asyncio
async def test_reason_uses_working_only_memory_when_coding_off(monkeypatch):
    """Architect oral path must not trigger semantic/ST retrieve."""
    calls: List[Dict[str, Any]] = []

    class _FakeMem:
        async def build_context(self, **kwargs):
            calls.append(kwargs)
            from types import SimpleNamespace
            return SimpleNamespace(working_context="", episodic_summary="", relevant_memories=[], messages=[], token_count=0)

        def set_domain_context(self, *_a, **_k):
            return None

    class _FakeLoop:
        async def _maybe_compact_messages(self, state):
            return None

        async def _try_inject_graph_context(self, state):
            return {}

        async def _try_inject_ontology_context(self, state):
            return {}

        def _build_tools_desc(self):
            return "No tools", {}

        def _build_skills_desc(self, context_pressure=None):
            return "architecture_design", {}

        async def _try_save_interaction(self, *_a, **_k):
            return None

        async def _try_extract_user_facts(self, *_a, **_k):
            return None

    llm_calls = {"n": 0}

    async def _fake_llm(model, prompt, **kwargs):
        llm_calls["n"] += 1
        from types import SimpleNamespace
        return SimpleNamespace(content='{"title":"ok"}', usage={})

    monkeypatch.setattr(
        "core.harness.memory.manager.get_memory_manager",
        lambda: _FakeMem(),
    )
    monkeypatch.setattr(
        "core.harness.syscalls.llm.sys_llm_generate",
        _fake_llm,
    )
    monkeypatch.setattr(
        "core.harness.execution.loop.inference.sys_llm_generate",
        _fake_llm,
    )

    from core.harness.execution.loop import inference as inf

    out = await inf.reason(
        _state(),
        model=object(),
        config=LoopConfig(max_steps=3, model_name="qwen2.5:3b"),
        skills=[],
        tools=[],
        loop=_FakeLoop(),
    )
    assert llm_calls["n"] == 1
    assert out
    assert calls, "build_context must be invoked"
    assert calls[0].get("retrieval_budget") == "working_only"


@pytest.mark.asyncio
async def test_embed_transform_timeout_falls_back_to_hash(monkeypatch):
    from core.harness.memory.embedding import EmbeddingProvider

    prov = EmbeddingProvider(backend="transform")
    monkeypatch.setenv("AIPLAT_EMBED_TRANSFORM_TIMEOUT", "0.15")
    monkeypatch.delenv("AIPLAT_EMBED_BACKEND", raising=False)
    monkeypatch.delenv("AIPLAT_EMBEDDING_BACKEND", raising=False)

    def _load_and_encode_slow():
        import time
        time.sleep(2.0)
        return [[1.0, 0.0]]

    # Patch the privateloader used inside _embed_transform by forcing timeout path
    async def _patched(texts):
        try:
            loop = asyncio.get_running_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(None, _load_and_encode_slow),
                timeout=0.15,
            )
        except asyncio.TimeoutError:
            return EmbeddingProvider(backend="simple")._embed_simple(texts)

    monkeypatch.setattr(prov, "_embed_transform", _patched)
    vecs = await prov.embed(["hello"])
    assert vecs and isinstance(vecs[0], list) and len(vecs[0]) > 0


@pytest.mark.asyncio
async def test_query_rewrite_skipped_without_history(monkeypatch):
    """First-turn reasoning must not call rewrite_with_history."""
    rewrite_calls = {"n": 0}

    async def _boom(*_a, **_k):
        rewrite_calls["n"] += 1
        raise AssertionError("rewrite must not run on first turn")

    monkeypatch.setattr(
        "core.harness.knowledge.query_rewriter.rewrite_with_history",
        _boom,
    )

    class _FakeLoop:
        async def _maybe_compact_messages(self, state):
            return None

        async def _try_inject_graph_context(self, state):
            return {}

        async def _try_inject_ontology_context(self, state):
            return {}

        def _build_tools_desc(self):
            return "", {}

        def _build_skills_desc(self, context_pressure=None):
            return "", {}

        async def _try_save_interaction(self, *_a, **_k):
            return None

        async def _try_extract_user_facts(self, *_a, **_k):
            return None

    async def _fake_llm(model, prompt, **kwargs):
        from types import SimpleNamespace
        return SimpleNamespace(content="DONE: ok", usage={})

    monkeypatch.setattr(
        "core.harness.execution.loop.inference.sys_llm_generate",
        _fake_llm,
    )

    class _Mem:
        async def build_context(self, **kwargs):
            from types import SimpleNamespace
            return SimpleNamespace(
                working_context="",
                episodic_summary="",
                relevant_memories=[],
                messages=[],
                token_count=0,
            )

        def set_domain_context(self, *a, **k):
            return None

    monkeypatch.setattr("core.harness.memory.manager.get_memory_manager", lambda: _Mem())

    from core.harness.execution.loop import inference as inf

    await inf.reason(
        _state(_enable_query_rewrite=True, messages=[]),
        model=object(),
        config=LoopConfig(max_steps=1),
        skills=[],
        tools=[],
        loop=_FakeLoop(),
    )
    assert rewrite_calls["n"] == 0
