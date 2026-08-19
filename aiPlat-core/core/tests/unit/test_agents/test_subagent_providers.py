"""P1-A3 subagent provider tests — provider abstraction, wiring, continuation."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core.apps.agents.subagent.coordinator import SubagentCoordinator
from core.apps.agents.subagent.providers import (
    ACPProvider,
    InProcessProvider,
    ProcessProvider,
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

    def test_factories_expose_three_providers(self):
        factories = get_provider_factories()
        assert set(factories.keys()) == {"in_process", "acp", "process"}

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
        assert "process" in providers  # P3-2: fork-style provider registered
        assert len(providers) >= 3  # P1-A3 acceptance: ≥2 providers, P3-2 → 3

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


class TestProcessProvider:
    """P3-2 fork-style provider: subprocess isolation + JSON protocol."""

    def test_capabilities_external_isolation(self):
        p = ProcessProvider()
        assert p.capabilities.external is True
        assert p.capabilities.isolation is True
        assert p.capabilities.continuation is False
        assert p.name == "process"

    def test_roundtrip_with_fake_runner(self, tmp_path, monkeypatch):
        """Spawn a fake runner subprocess; verify JSON stdin→stdout roundtrip."""
        runner = tmp_path / "fake_runner.py"
        runner.write_text(
            "import json, sys\n"
            "payload = json.loads(sys.stdin.read())\n"
            "json.dump({'ok': True, 'output': 'echo:' + payload['task'],\n"
            "           'instance_id': 'process:' + payload['name']}, sys.stdout)\n",
            encoding="utf-8",
        )
        monkeypatch.setenv(
            "PYTHONPATH",
            str(tmp_path) + ":" + __import__("os").environ.get("PYTHONPATH", ""),
        )
        p = ProcessProvider(runner_module="fake_runner", timeout=30)
        result = asyncio_run(p.start(name="pm_agent", task="build plan"))
        assert result.ok is True
        assert result.output == "echo:build plan"
        assert result.instance_id == "process:pm_agent"

    def test_bad_json_fails_loud(self, tmp_path, monkeypatch):
        runner = tmp_path / "bad_runner.py"
        runner.write_text("print('not json')\n", encoding="utf-8")
        monkeypatch.setenv(
            "PYTHONPATH",
            str(tmp_path) + ":" + __import__("os").environ.get("PYTHONPATH", ""),
        )
        p = ProcessProvider(runner_module="bad_runner", timeout=30)
        result = asyncio_run(p.start(name="x", task="t"))
        assert result.ok is False
        assert "bad JSON" in result.error

    def test_runner_module_failure_fails_loud(self, monkeypatch):
        p = ProcessProvider(runner_module="no_such_module_xyz", timeout=30)
        result = asyncio_run(p.start(name="x", task="t"))
        assert result.ok is False
        assert result.error


class TestProcessRunnerModule:
    """process_runner.py JSON contract (error branch does not need the agent stack)."""

    def test_main_bad_input_emits_json(self, tmp_path, monkeypatch):
        import json
        import sys
        import io

        from core.apps.agents.subagent import process_runner

        monkeypatch.setattr(sys, "stdin", io.StringIO("not-json{{{"))
        out = io.StringIO()
        monkeypatch.setattr(sys, "stdout", out)
        process_runner.main()
        data = json.loads(out.getvalue().strip())
        assert data["ok"] is False
        assert "process_runner" in data["error"]

    def test_main_emits_ok_false_on_empty_input(self, tmp_path, monkeypatch):
        import json
        import sys
        import io

        from core.apps.agents.subagent import process_runner

        # Empty payload → empty name/task; stub _execute so no agent stack runs.
        monkeypatch.setattr(
            process_runner, "_execute",
            lambda name, task, context: {"ok": False, "error": "no-op stub",
                                         "output": "", "instance_id": "", "can_continue": False},
        )
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))
        out = io.StringIO()
        monkeypatch.setattr(sys, "stdout", out)
        process_runner.main()
        data = json.loads(out.getvalue().strip())
        assert data["ok"] is False


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
