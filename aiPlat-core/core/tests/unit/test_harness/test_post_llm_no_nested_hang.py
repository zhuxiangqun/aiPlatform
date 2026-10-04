"""Regression: post-LLM memory must not await nested sys_llm_generate on ReAct hot path."""
from __future__ import annotations

import asyncio
from typing import List

import pytest

from core.harness.memory.manager import MemoryConfig, MemoryManager
from core.harness.utils.local_llm_recover import (
    looks_like_local_llm,
    local_llm_inflight,
)


@pytest.mark.asyncio
async def test_save_interaction_uses_rule_summary_not_awaited_llm(monkeypatch):
    """When episodic update_interval is hit, hot path must not await nested LLM."""
    nested: List[str] = []

    async def _boom_llm(prompt: str):
        nested.append(str(prompt)[:80])
        await asyncio.sleep(30)  # would wedge ReAct if awaited
        return '{"summary":"should-not-block","key_points":[],"tasks":[],"decisions":[]}'

    mgr = MemoryManager(
        MemoryConfig(use_llm_summary=True, episodic_update_interval=2, model=object())
    )
    monkeypatch.setattr(mgr, "_get_llm_callable", lambda background=False: _boom_llm)

    await mgr.save_interaction("u1", "a1", stability="medium")
    # Second interaction crosses interval=2 → would previously await LLM summary
    await asyncio.wait_for(
        mgr.save_interaction("u2", "a2", stability="medium"),
        timeout=2.0,
    )
    assert mgr._episodic.get_summary()  # rule summary applied
    # Nested LLM may be scheduled as bg task — must not have blocked save.
    await asyncio.sleep(0.05)
    # Cancel any pending polish tasks so the test process exits cleanly
    pending = [t for t in asyncio.all_tasks() if not t.done() and t is not asyncio.current_task()]
    for t in pending:
        t.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


@pytest.mark.asyncio
async def test_bg_polish_does_not_raise_into_caller(monkeypatch):
    mgr = MemoryManager(MemoryConfig(use_llm_summary=True, model=object()))

    async def _fail(_prompt: str):
        raise RuntimeError("polish failed")

    await mgr._bg_polish_episodic_summary(_fail)  # must swallow


@pytest.mark.asyncio
async def test_local_llm_inflight_serializes():
    assert looks_like_local_llm(model_name="qwen2.5-coder:7b")
    assert looks_like_local_llm(provider="ollama")
    assert not looks_like_local_llm(provider="openai", base_url="https://api.openai.com/v1")

    order: List[str] = []
    hold = asyncio.Event()

    async def _holder():
        async with local_llm_inflight(model_name="qwen2.5:3b", acquire_timeout=5.0):
            order.append("a_in")
            await hold.wait()
            order.append("a_out")

    async def _waiter():
        await asyncio.sleep(0.05)
        async with local_llm_inflight(model_name="qwen2.5:3b", acquire_timeout=5.0):
            order.append("b")

    t1 = asyncio.create_task(_holder())
    t2 = asyncio.create_task(_waiter())
    await asyncio.sleep(0.1)
    assert order == ["a_in"]
    hold.set()
    await asyncio.wait_for(asyncio.gather(t1, t2), timeout=3.0)
    assert order == ["a_in", "a_out", "b"]


@pytest.mark.asyncio
async def test_local_llm_inflight_noop_for_remote():
    """Remote providers must not take the local single-flight slot."""
    async with local_llm_inflight(
        provider="openai",
        base_url="https://api.openai.com/v1",
        acquire_timeout=1.0,
    ):
        async with local_llm_inflight(
            provider="openai",
            base_url="https://api.openai.com/v1",
            acquire_timeout=1.0,
        ):
            pass


@pytest.mark.asyncio
async def test_post_generate_save_path_completes_under_hanging_bg_llm(monkeypatch):
    """Mimic inference.reason's post-generate save: must finish even if bg LLM hangs."""
    mgr = MemoryManager(
        MemoryConfig(use_llm_summary=True, episodic_update_interval=1, model=object())
    )

    async def _nested_would_hang(prompt: str, **_k):
        await asyncio.sleep(60)
        return "{}"

    monkeypatch.setattr(mgr, "_get_llm_callable", lambda background=False: _nested_would_hang)

    # Same sequence as inference.reason after sys_llm_generate returns
    await asyncio.wait_for(
        mgr.save_interaction(
            user_message="请输出架构草稿",
            assistant_message='{"type":"skill_call","name":"architecture_design"}',
            stability="medium",
        ),
        timeout=2.0,
    )
    assert "architecture" in (mgr._episodic.get_summary() or "").lower() or mgr._episodic.get_summary()
    for t in list(asyncio.all_tasks()):
        if t is not asyncio.current_task() and not t.done():
            t.cancel()


def test_post_generate_does_not_construct_model_manager():
    from core.harness.utils import model_injection as mi

    prev = mi._model_manager_cache
    mi._model_manager_cache = None
    try:
        mi._record_cached_model_outcome("qwen2.5:3b", success=True)
        hits: List[str] = []

        class _Mgr:
            def record_success(self, n):
                hits.append(f"ok:{n}")

            def record_failure(self, n):
                hits.append(f"fail:{n}")

        mi._model_manager_cache = _Mgr()
        mi._record_cached_model_outcome("qwen2.5:3b", success=True)
        mi._record_cached_model_outcome("qwen2.5:3b", success=False)
        assert hits == ["ok:qwen2.5:3b", "fail:qwen2.5:3b"]
    finally:
        mi._model_manager_cache = prev


def test_llm_hot_path_uses_cached_outcome_helper():
    from pathlib import Path

    core = Path(__file__).resolve().parents[3]
    llm_src = (core / "harness/syscalls/llm.py").read_text(encoding="utf-8")
    inf_src = (core / "harness/execution/loop/inference.py").read_text(encoding="utf-8")
    assert "_record_cached_model_outcome" in llm_src
    assert "_get_cached_model_manager().record_success" not in llm_src
    assert "_get_cached_model_manager().record_failure" not in llm_src
    assert "ensure_future" in inf_src
    assert "_try_save_interaction" in inf_src
