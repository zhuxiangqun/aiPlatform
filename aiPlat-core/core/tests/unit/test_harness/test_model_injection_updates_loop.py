import os

import pytest


class DummyLoop:
    def __init__(self):
        self._model = None

    def set_model(self, m):
        self._model = m


class DummyAgent:
    def __init__(self):
        self._model = None
        self._loop = DummyLoop()

    def set_model(self, m):
        # simulate common bug: agent.set_model only updates agent._model
        self._model = m


@pytest.mark.anyio
async def test_ensure_agent_model_updates_loop(monkeypatch):
    # Stub adapter creation — hermetic CI has no remote credentials
    class _StubModel:
        pass

    monkeypatch.setattr(
        "core.harness.utils.model_injection.create_selected_adapter",
        lambda **_kw: _StubModel(),
    )

    from core.harness.utils.model_injection import ensure_agent_model

    a = DummyAgent()
    ensure_agent_model(a, model_name="gpt-4")

    assert a._model is not None
    assert a._loop._model is not None
    # should be the same instance
    assert a._model is a._loop._model

