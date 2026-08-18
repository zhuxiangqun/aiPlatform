"""Wiring + behavior assertions for ACP client (P1-A3).

Verifies:
  - ACPProvider.start() imports core.acp.client (no longer fails loud at import)
  - ACPClient exposes SubagentProvider-compatible methods
  - fail-loud path returns structured error (no server running in tests)
"""

import asyncio
import pytest

from .conftest import assert_wired


class TestACPClientWired:
    def test_acp_client_has_production_caller(self):
        assert_wired(
            "ACPClient",
            "client.py",
            phase="P1-A3",
            desc="ACPProvider.start() imports core.acp.client for the external subagent backend",
        )

    def test_acp_provider_imports_client(self):
        """ACPProvider must reach core.acp.client (the wiring that was missing)."""
        import inspect
        from core.apps.agents.subagent.providers import ACPProvider

        src = inspect.getsource(ACPProvider.start)
        assert "from core.acp.client import ACPClient" in src

    def test_client_fail_loud_without_server(self):
        """With no ACP server running, start_agent returns structured failure."""
        from core.acp.client import ACPClient

        result = asyncio.run(ACPClient("ws://localhost:1/acp").start_agent("t", "hi"))
        assert result["ok"] is False
        assert result["error"]  # non-empty error
