"""Wiring + behavior assertions for ProcessProvider (P3-2, DSH fork 借鉴).

Verifies:
  - ProcessProvider has a production caller chain (factory → coordinator)
  - process_runner module is referenced by ProcessProvider.start (subprocess wiring)
  - the "process" provider is registered in the factory table
"""

import asyncio

from .conftest import assert_wired


class TestProcessProviderWired:
    def test_process_provider_has_production_caller(self):
        assert_wired(
            "ProcessProvider",
            "providers.py",
            phase="P3-2",
            desc="ProcessProvider registered in _PROVIDER_FACTORIES, consumed by "
                 "SubagentCoordinator.get_provider/list_providers (production paths)",
        )

    def test_runner_module_referenced_by_provider(self):
        """process_runner.py must be reachable from ProcessProvider.start (subprocess -m)."""
        import inspect
        from core.apps.agents.subagent.providers import ProcessProvider

        src = inspect.getsource(ProcessProvider.__init__) + inspect.getsource(ProcessProvider.start)
        assert "core.apps.agents.subagent.process_runner" in src

    def test_process_registered_in_factory(self):
        from core.apps.agents.subagent.providers import get_provider_factories

        factories = get_provider_factories()
        assert "process" in factories

    def test_process_runner_importable(self):
        import core.apps.agents.subagent.process_runner as runner

        assert callable(runner.main)
        assert callable(runner._execute)

    def test_process_provider_start_returns_provider_result(self):
        from core.apps.agents.subagent.providers import ProcessProvider, ProviderResult

        p = ProcessProvider(runner_module="no_such_module_xyz", timeout=5)
        result = asyncio.run(p.start(name="x", task="t"))
        assert isinstance(result, ProviderResult)
        assert result.ok is False  # fail-loud, never fake success
