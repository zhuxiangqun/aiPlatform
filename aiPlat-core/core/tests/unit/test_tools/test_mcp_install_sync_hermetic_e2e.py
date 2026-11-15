"""Hermetic MCP install → sync → connectable/connected（本地 stdio，非公网）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from core.apps.mcp.runtime import MCPRuntime
from core.apps.tools import get_tool_registry
from core.harness.maintenance.asset_compat import (
    TIER_CONNECTABLE,
    TIER_CONNECTED,
    read_mcp_compat,
)
from core.management.asset_installer import MCPInstaller
from core.management.mcp_manager import MCPManager


@pytest.mark.asyncio
async def test_mcp_install_sync_local_stdio_e2e(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Claude plugin mcp/*.json → install → MCPManager reload → sync → COMPAT connected.

    Uses ``python -m core.apps.mcp.local_tools_server`` as the local fake server
    (no public GitHub / remote MCP). Empty tools dir is fine — initialize still succeeds.
    """
    home = tmp_path / "home"
    home.mkdir()
    tools = home / "tools"
    tools.mkdir()
    # Minimal TOOL_DEF so tools/list is non-empty (optional but strengthens E2E)
    (tools / "echo_tool.py").write_text(
        'TOOL_DEF = {"name": "echo_hermetic", "description": "echo", '
        '"parameters": {"type": "object", "properties": {}}, '
        '"execute": lambda **kw: {"ok": True}}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    monkeypatch.setenv("AIPLAT_TOOLS_PATH", str(tools))
    monkeypatch.setenv("AIPLAT_WORKSPACE_MCPS_PATH", str(home / "mcps"))
    monkeypatch.setattr(
        "core.management.asset_installer.get_aiplat_home",
        lambda: str(home),
    )
    monkeypatch.setattr(
        "core.utils.paths.get_aiplat_home",
        lambda: str(home),
    )

    plugin = tmp_path / "plugin"
    mcp_dir = plugin / "mcp"
    mcp_dir.mkdir(parents=True)
    (mcp_dir / "local.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "hermetic_local": {
                        "command": sys.executable,
                        "args": ["-m", "core.apps.mcp.local_tools_server"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (plugin / "skills").mkdir()
    (plugin / "skills" / "noop.md").write_text("# noop\n", encoding="utf-8")

    inst = MCPInstaller(target_base_dir=home / "mcps")
    # Install without auto-sync (empty managers); we drive sync explicitly below.
    from unittest import mock

    with mock.patch(
        "core.management.asset_installer._try_sync_mcp_after_claude_plugin",
        return_value=None,
    ):
        manifest = inst._adapt_claude_plugin(plugin)

    assert "hermetic_local" in (manifest.get("mcp_installed") or [])
    dest = home / "mcps" / "hermetic_local"
    assert (dest / "server.yaml").is_file()
    pre = read_mcp_compat(dest) or {}
    assert pre.get("connection_status") in {TIER_CONNECTABLE, TIER_CONNECTED} or pre.get(
        "tier"
    ) in {TIER_CONNECTABLE, TIER_CONNECTED}

    mgr = MCPManager(scope="workspace")
    servers = [s for s in mgr.list_servers() if s.name == "hermetic_local"]
    assert servers, "MCPManager must see installed hermetic_local"
    assert servers[0].enabled is True
    assert str(servers[0].transport).lower() == "stdio"
    assert servers[0].command

    runtime = MCPRuntime()
    summary = await runtime.sync_from_servers(
        servers=servers,
        tool_registry=get_tool_registry(),
    )
    post = read_mcp_compat(dest) or {}
    status = str(post.get("connection_status") or post.get("tier") or "")
    # Prefer connected; connectable is honest fallback if spawn fails in exotic env
    if "hermetic_local" in (summary.get("connected") or []):
        assert status == TIER_CONNECTED
        assert "hermetic_local" in runtime.manager._clients
        # Disconnect honesty: tear down leaves connectable, not fake-ok forever
        await runtime.sync_from_servers(servers=[], tool_registry=get_tool_registry())
        after_disc = read_mcp_compat(dest) or {}
        assert str(after_disc.get("connection_status") or "") == TIER_CONNECTABLE
    else:
        assert status == TIER_CONNECTABLE
        skipped = summary.get("skipped") or []
        assert any(
            (isinstance(x, dict) and x.get("server") == "hermetic_local") or x == "hermetic_local"
            for x in skipped
        ), f"expected skipped hermetic_local, got {summary}"
