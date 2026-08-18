"""P1-A3 subagent provider tests — provider abstraction, wiring, continuation."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core.apps.agents.subagent.coordinator import SubagentCoordinator
from core.apps.agents.subagent.providers import (
    ACPProvider,
    InProcessProvider,
    ProviderCapabilities,
    ProviderResult,
    SubagentProvider,
    default_provider_name,
    get_provider_factories,
)


class TestProviderAbstraction:
    def test_abstract_class_exists(self):
        assert issubclass(SubagentProvider, object)
        assert hasattr(SubagentProvider, "start")
        assert hasattr(SubagentProvider, "continuation")
        assert hasattr(SubagentProvider, "interrupt")

    def test_capabilities_dataclass(self):
        caps = ProviderCapabilities()
        assert caps.start is True
        assert caps.continuation is False  # default: not continuable
        assert caps.isolation is True

    def test_factories_expose_both_providers(self):
        factories = get_provider_factories()
        assert set(factories.keys()) == {"in_process", "acp"}

    def test_default_provider_name_env(self, monkeypatch):
        monkeypatch.setenv("AIPLAT_SUBAGENT_PROVIDER", "acp")
        assert default_provider_name() == "acp"
        monkeypatch.delenv("AIPLAT_SUBAGENT_PROVIDER")
        assert default_provider_name() == "in_process"


class TestCoordinatorProviders:
    def test_list_providers_has_two(self):
        c = SubagentCoordinator()
        providers = c.list_providers()
        assert "in_process" in providers
        assert len(providers) >= 2  # P1-A3 acceptance: ≥2 providers

    def test_get_provider_default(self):
        c = SubagentCoordinator()
        p = c.get_provider("in_process")
        assert isinstance(p, InProcessProvider)

    def test_get_provider_unknown_raises(self):
        c = SubagentCoordinator()
        with pytest.raises(ValueError):
            c.get_provider("no_such_provider")

    def test_in_process_start_fails_loud_without_registry(self):
        """No fake success when subagent not wired."""
        c = SubagentCoordinator()
        p = c.get_provider("in_process")
        result = asyncio_run(p.start(name="ghost", task="t"))
        assert result.ok is False
        assert result.error

    def test_acp_provider_capabilities_external(self):
        p = ACPProvider()
        assert p.capabilities.external is True
        assert p.capabilities.output_schema is True

    def test_acp_fails_loud_without_client(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "core.acp.client":
                raise ImportError("no acp client")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        p = ACPProvider()
        result = asyncio_run(p.start(name="x", task="t"))
        assert result.ok is False
        assert "not available" in result.error


class TestContinuation:
    def test_send_message_fails_loud_when_not_continuable(self):
        c = SubagentCoordinator()
        r = asyncio_run(c.send_message("x:y", "hello"))
        assert r.success is False
        assert r.error  # in-process continuation unsupported → loud

    def test_instance_status_three_states(self):
        c = SubagentCoordinator()
        assert c.get_instance_status() == {}

    def test_execute_parallel_provider_path(self):
        c = SubagentCoordinator()
        res = asyncio_run(c.execute_parallel("task", ["ghost"], provider="in_process"))
        assert res[0].success is False  # fail-loud, not fake success

    def test_execute_parallel_default_path(self):
        c = SubagentCoordinator()
        res = asyncio_run(c.execute_parallel("task", ["ghost"]))
        assert res[0].success is False  # registry miss, same as before


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
