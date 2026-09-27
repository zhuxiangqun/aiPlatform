"""Agent AI audit must flag bound tools that are registered but not listed."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_audit_flags_registered_but_unlisted_tool(tmp_path, monkeypatch):
    home = tmp_path / ".aiplat"
    agent_dir = home / "agents" / "audit_tool_gate"
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text(
        "---\n"
        "name: audit_tool_gate\n"
        "agent_type: react\n"
        "status: ready\n"
        "required_tools:\n"
        "  - routed_retrieve\n"
        "config:\n"
        "  system_prompt: you are a test agent\n"
        "---\n"
        "## Persona\n"
        "test\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(home))

    class _Reg:
        def list_tools(self):
            return ["routed_retrieve", "file_operations"]

    monkeypatch.setattr(
        "core.apps.tools.base.get_tool_registry",
        lambda: _Reg(),
    )
    # Default lifecycle = draft (empty store under AIPLAT_HOME)
    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_tool_gate")
    cats = {i["category"] for i in resp.issues}
    assert "tool_not_listed" in cats
    hit = next(i for i in resp.issues if i["category"] == "tool_not_listed")
    assert hit["current"] == "routed_retrieve"
    assert hit["severity"] == "error"
    assert hit.get("fix", {}).get("type") == "remove_tool"
    assert resp.summary["health"] in ("C", "D")


@pytest.mark.asyncio
async def test_audit_passes_listed_tool(tmp_path, monkeypatch):
    home = tmp_path / ".aiplat"
    agent_dir = home / "agents" / "audit_tool_ok"
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text(
        "---\n"
        "name: audit_tool_ok\n"
        "agent_type: react\n"
        "status: ready\n"
        "required_tools:\n"
        "  - file_operations\n"
        "config:\n"
        "  system_prompt: you are a test agent\n"
        "---\n"
        "## Persona\n"
        "test\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(home))

    from core.apps.tools.lifecycle import set_tool_status

    set_tool_status("file_operations", "listed")

    class _Reg:
        def list_tools(self):
            return ["file_operations", "routed_retrieve"]

    monkeypatch.setattr(
        "core.apps.tools.base.get_tool_registry",
        lambda: _Reg(),
    )
    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_tool_ok")
    assert not any(i["category"] == "tool_not_listed" for i in resp.issues)
    assert not any(i["category"] == "invalid_tool" for i in resp.issues)
