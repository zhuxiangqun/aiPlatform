"""Claude Plugin mcp/*.json → ~/.aiplat/mcps/<id> + COMPAT connectable."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from core.harness.maintenance.asset_compat import TIER_CONNECTABLE, read_mcp_compat
from core.management.asset_installer import MCPInstaller


def test_claude_plugin_mcp_json_auto_register(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(
        "core.management.asset_installer.get_aiplat_home",
        lambda: str(home),
    )

    plugin = tmp_path / "plugin"
    mcp_dir = plugin / "mcp"
    mcp_dir.mkdir(parents=True)
    (mcp_dir / "demo.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "demo_srv": {
                        "command": "npx",
                        "args": ["-y", "example-mcp-server"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (plugin / "skills").mkdir()
    (plugin / "skills" / "noop.md").write_text("# noop\n", encoding="utf-8")

    inst = MCPInstaller(target_base_dir=home / "mcps")
    with mock.patch(
        "core.management.asset_installer._try_sync_mcp_after_claude_plugin",
        return_value=None,
    ):
        manifest = inst._adapt_claude_plugin(plugin)

    assert any(str(x).startswith("mcp:") for x in manifest.get("converted") or [])
    assert "demo_srv" in (manifest.get("mcp_installed") or [])
    dest = home / "mcps" / "demo_srv"
    assert (dest / "server.yaml").is_file()
    yaml_text = (dest / "server.yaml").read_text(encoding="utf-8")
    assert "name: demo_srv" in yaml_text
    compat = read_mcp_compat(dest) or {}
    assert compat.get("connection_status") == TIER_CONNECTABLE or compat.get("tier") == TIER_CONNECTABLE


def test_claude_plugin_path_secure_scan_before_adapt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Blocked suffix in plugin tree must fail before MCP lands under home."""
    from core.harness.maintenance.asset_secure_scan import AssetSecureScanError

    home = tmp_path / "home_scan"
    home.mkdir()
    monkeypatch.setattr(
        "core.management.asset_installer.get_aiplat_home",
        lambda: str(home),
    )
    plugin = tmp_path / "plugin_bad"
    mcp_dir = plugin / "mcp"
    mcp_dir.mkdir(parents=True)
    (mcp_dir / "ok.json").write_text(
        json.dumps({"mcpServers": {"ok_srv": {"command": "echo"}}}),
        encoding="utf-8",
    )
    (plugin / "skills").mkdir()
    (plugin / "skills" / "noop.md").write_text("# noop\n", encoding="utf-8")
    (plugin / "evil.exe").write_bytes(b"MZ")

    inst = MCPInstaller(target_base_dir=home / "mcps")
    with pytest.raises(AssetSecureScanError):
        inst.install_from_path(path=str(plugin), skip_claude_plugin=False)
    assert not (home / "mcps" / "ok_srv").exists()


def test_single_server_json_without_wrapper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "home2"
    home.mkdir()
    monkeypatch.setattr(
        "core.management.asset_installer.get_aiplat_home",
        lambda: str(home),
    )
    plugin = tmp_path / "plugin2"
    mcp_dir = plugin / "mcp"
    mcp_dir.mkdir(parents=True)
    (mcp_dir / "solo.json").write_text(
        json.dumps({"name": "solo_mcp", "command": "echo", "args": ["hi"]}),
        encoding="utf-8",
    )
    inst = MCPInstaller(target_base_dir=home / "mcps")
    manifest = inst._adapt_claude_plugin(plugin)
    assert "solo_mcp" in (manifest.get("mcp_installed") or [])
    assert (home / "mcps" / "solo_mcp" / "server.yaml").is_file()
