from types import SimpleNamespace
import importlib

import anyio
import pytest


@pytest.mark.integration
def test_mcp_prod_stdio_denied_records_syscall_event(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_ENV", "prod")

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.harness.kernel.runtime import set_kernel_runtime
    from core.apps.mcp.runtime import MCPRuntime
    from core.apps.tools.base import get_tool_registry

    store = ExecutionStore(ExecutionStoreConfig(db_path=str(tmp_path / "exec.sqlite3")))
    anyio.run(store.init)
    set_kernel_runtime(SimpleNamespace(execution_store=store))

    runtime = MCPRuntime()
    server = SimpleNamespace(name="deny_stdio", enabled=True, transport="stdio", metadata={"policy": {"prod_allowed": False}})

    async def _run():
        summary = await runtime.sync_from_servers(servers=[server], tool_registry=get_tool_registry())
        return summary

    summary = anyio.run(_run)
    assert summary["connected"] == []
    assert summary["skipped"]

    async def _list():
        return await store.list_syscall_events(limit=50, offset=0, kind="mcp")

    events = anyio.run(_list)
    assert events["total"] >= 1
    assert any(e.get("status") == "prod_denied" and e.get("error_code") == "PROD_DENIED" for e in events["items"])
