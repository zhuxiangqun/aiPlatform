"""Hang-fix: pre-LLM graph/ontology inject must not block the event loop."""
from __future__ import annotations

import asyncio

import pytest

from core.harness.execution.loop.graph_injector import (
    inject_graph_context,
    inject_ontology_context,
    wants_code_graph,
    wants_ontology_inject,
)
from core.harness.interfaces.loop import LoopState, LoopStateEnum


def _state(**ctx) -> LoopState:
    base = {
        "task": "现场巡检报修架构草稿",
        "messages": [],
        "_coding_policy_profile": "off",
        "_agent_id": "architect_agent",
    }
    base.update(ctx)
    return LoopState(current=LoopStateEnum.INIT, context=base)


def test_wants_code_graph_off_for_workspace_profile():
    assert wants_code_graph(_state(_coding_policy_profile="off")) is False


def test_wants_code_graph_on_for_karpathy():
    assert wants_code_graph(_state(_coding_policy_profile="karpathy_v1")) is True


def test_wants_ontology_off_for_workspace_profile():
    assert wants_ontology_inject(_state(_coding_policy_profile="off")) is False


def test_wants_ontology_on_for_coding_profile():
    assert wants_ontology_inject(_state(_coding_policy_profile="karpathy_v1")) is True


@pytest.mark.asyncio
async def test_inject_ontology_skips_classify_when_coding_off(monkeypatch):
    """Regression: architect step_1 hang — DomainRouter embed before first LLM."""
    calls = {"n": 0}

    class _Boom:
        def classify(self, *_a, **_k):
            calls["n"] += 1
            raise AssertionError("ontology classify must not run for coding_policy=off")

    monkeypatch.setattr(
        "core.harness.knowledge.domain_router.DomainRouter",
        lambda: _Boom(),
    )
    st = _state(_coding_policy_profile="off")
    hints = await inject_ontology_context(st)
    assert hints.get("ontology_skipped") is True
    assert st.context.get("_ontology_injected") is True
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_inject_graph_skips_code_intel_when_coding_off(monkeypatch):
    calls = {"n": 0}

    def _boom(*_a, **_k):
        calls["n"] += 1
        raise AssertionError("code graph must not run for coding_policy=off")

    import core.harness.execution.loop.graph_injector as gi

    monkeypatch.setattr(gi, "_safe_code_intel", _boom)

    st = _state()
    hints = await inject_graph_context(st)
    assert hints.get("code_graph_skipped") is True
    assert st.context.get("_graph_loaded") is True
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_inject_graph_offloads_and_timeouts(monkeypatch):
    import core.harness.execution.loop.graph_injector as gi

    def _slow(_task):
        import time

        time.sleep(2.0)
        return {"related": [{"file": "a.py", "imports": []}]}

    monkeypatch.setenv("AIPLAT_FORCE_CODE_GRAPH_INJECT", "1")
    monkeypatch.setenv("AIPLAT_CODE_GRAPH_INJECT_TIMEOUT", "0.2")
    monkeypatch.setattr(gi, "_safe_code_intel", _slow)
    monkeypatch.setattr(gi, "_light_wiki_hint", lambda *_a, **_k: {})
    monkeypatch.setattr(gi, "_skill_deps_hint", lambda: {})

    st = _state(_coding_policy_profile="karpathy_v1")
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    hints = await inject_graph_context(st)
    elapsed = loop.time() - t0
    assert hints.get("code_graph_timeout") is True
    assert elapsed < 1.5  # must not block ~2s sync sleep on the loop


@pytest.mark.asyncio
async def test_llm_classify_fail_open_on_running_loop():
    from core.harness.knowledge.domain_router import DomainRouter

    r = DomainRouter()
    monkey_domains = ["ai-knowledge", "fde-delivery"]

    r.list_domains = lambda: monkey_domains  # type: ignore
    r._ensure_built = lambda: None  # type: ignore
    r._label_index = {}
    r._domain_vectors = {}
    r._t1_label_match = lambda *_a, **_k: None  # type: ignore
    r._t2_embed_score = lambda *_a, **_k: None  # type: ignore
    r._load_registry = lambda: {  # type: ignore
        "fallback_domain": "ai-knowledge",
        "domains": {d: {"name": d} for d in monkey_domains},
        "routing": {"embedding": {"min_confidence": 0.99, "min_margin": 0.5}},
    }

    async def _probe():
        return r.classify("完全随机的跨域问题 xyz-no-label-match")

    did = await asyncio.wait_for(_probe(), timeout=2.0)
    assert did == "ai-knowledge"


@pytest.mark.asyncio
async def test_inject_ontology_uses_thread(monkeypatch):
    class _R:
        def classify(self, q):
            return "ai-knowledge"

    monkeypatch.setattr(
        "core.harness.knowledge.domain_router.DomainRouter",
        lambda: _R(),
    )
    monkeypatch.setattr(
        "os.path.exists",
        lambda *_a, **_k: False,
    )

    st = _state(task="供应链仓储优化", _coding_policy_profile="karpathy_v1")
    hints = await inject_ontology_context(st)
    assert hints.get("ontology", {}).get("domain_id") == "ai-knowledge"
    assert st.context.get("_ontology_injected") is True
    assert not hints.get("ontology_skipped")
