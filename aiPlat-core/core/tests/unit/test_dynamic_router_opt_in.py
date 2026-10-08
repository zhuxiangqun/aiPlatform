"""W5: DynamicRouter / LLM supervisor is opt-in."""
from __future__ import annotations

import pytest

from core.schemas_builder import PipelineStageConfig


def _stages(n: int = 3, mode: str = "llm"):
    return [
        PipelineStageConfig(id=f"s{i}", agent_id=f"a{i}", order=i, routing_mode=mode)
        for i in range(n)
    ]


@pytest.fixture
def engine(monkeypatch):
    # Avoid heavy PipelineEngine init — call unbound method with a stub.
    from core.harness.execution.pipeline_engine import PipelineEngine

    class Stub:
        _should_use_dynamic_routing = PipelineEngine._should_use_dynamic_routing

    return Stub()


def test_static_mode_never_dynamic(engine, monkeypatch):
    monkeypatch.setenv("AIPLAT_DYNAMIC_ROUTER_ENABLED", "1")
    monkeypatch.setenv("AIPLAT_DYNAMIC_ROUTER_PERCENTAGE", "100")
    assert engine._should_use_dynamic_routing(_stages(mode="static"), "sess") is False


def test_llm_requires_enabled_flag(engine, monkeypatch):
    monkeypatch.delenv("AIPLAT_DYNAMIC_ROUTER_ENABLED", raising=False)
    monkeypatch.setenv("AIPLAT_DYNAMIC_ROUTER_PERCENTAGE", "100")
    assert engine._should_use_dynamic_routing(_stages(), "sess") is False


def test_llm_requires_percentage(engine, monkeypatch):
    monkeypatch.setenv("AIPLAT_DYNAMIC_ROUTER_ENABLED", "1")
    monkeypatch.delenv("AIPLAT_DYNAMIC_ROUTER_PERCENTAGE", raising=False)  # default 0
    assert engine._should_use_dynamic_routing(_stages(), "sess") is False


def test_llm_requires_min_stages(engine, monkeypatch):
    monkeypatch.setenv("AIPLAT_DYNAMIC_ROUTER_ENABLED", "1")
    monkeypatch.setenv("AIPLAT_DYNAMIC_ROUTER_PERCENTAGE", "100")
    monkeypatch.setenv("AIPLAT_DYNAMIC_ROUTER_MIN_STAGES", "3")
    assert engine._should_use_dynamic_routing(_stages(n=2), "sess") is False


def test_llm_opt_in_full(engine, monkeypatch):
    monkeypatch.setenv("AIPLAT_DYNAMIC_ROUTER_ENABLED", "1")
    monkeypatch.setenv("AIPLAT_DYNAMIC_ROUTER_PERCENTAGE", "100")
    monkeypatch.setenv("AIPLAT_DYNAMIC_ROUTER_MIN_STAGES", "3")
    assert engine._should_use_dynamic_routing(_stages(n=3), "sess") is True


def test_no_session_id_stays_off_when_partial_grayscale(engine, monkeypatch):
    monkeypatch.setenv("AIPLAT_DYNAMIC_ROUTER_ENABLED", "1")
    monkeypatch.setenv("AIPLAT_DYNAMIC_ROUTER_PERCENTAGE", "50")
    assert engine._should_use_dynamic_routing(_stages(), "") is False
