"""Deepened asset audits: agent bindings, tool params, workflow structure."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest


@pytest.mark.asyncio
async def test_audit_flags_invalid_mcp_binding(tmp_path, monkeypatch):
    home = tmp_path / ".aiplat"
    agent_dir = home / "agents" / "audit_mcp_bind"
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text(
        "---\n"
        "name: audit_mcp_bind\n"
        "agent_type: react\n"
        "status: ready\n"
        "mcp_servers:\n"
        "  - missing_mcp_xyz\n"
        "loop_type: react\n"
        "toolset: workspace_default\n"
        "permissions:\n"
        "  - llm:generate\n"
        "config:\n"
        "  system_prompt: you are a test agent\n"
        "---\n"
        "## Persona\n"
        "test\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    monkeypatch.setattr(
        "core.apps.tools.base.get_tool_registry",
        lambda: type("R", (), {"list_tools": lambda self: []})(),
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection.best_model_for_purpose_with_meta",
        lambda purpose, messages=None: {
            "model": "qwen2.5:7b",
            "model_tier": "medium",
            "model_purpose": purpose,
        },
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection._load_llm_profile",
        lambda: {"purpose_profiles": {"agent": {}, "chat": {}}},
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection._get_cached_model_manager",
        lambda: type(
            "M",
            (),
            {
                "select": lambda self, **k: None,
                "get_model_tier": lambda self, *a, **k: "unknown",
            },
        )(),
    )

    class _Mgr:
        def get_server(self, name):
            return None

    monkeypatch.setattr(
        "core.management.mcp_manager.MCPManager",
        lambda scope="workspace": _Mgr(),
    )

    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_mcp_bind")
    hit = next(i for i in resp.issues if i["category"] == "invalid_mcp")
    assert hit["current"] == "missing_mcp_xyz"
    assert hit["fix"]["type"] == "remove_mcp"


@pytest.mark.asyncio
async def test_audit_tool_empty_parameters_no_placeholder_fix(monkeypatch):
    """Empty properties must NOT offer one-click fake {input} schema (false green)."""
    class _Cfg:
        parameters = {"type": "object", "properties": {}}
        metadata = {"provenance": {}}
        description = "ok"

    class _Tool:
        _config = _Cfg()

        def get_description(self):
            return "ok"

    monkeypatch.setattr(
        "core.apps.tools.base.get_tool_registry",
        lambda: type("R", (), {"get": lambda self, n: _Tool() if n == "t1" else None})(),
    )
    monkeypatch.setattr("core.apps.tools.lifecycle.get_tool_status", lambda *a, **k: "listed")

    from core.api.routers.tools import audit_tool_config

    resp = await audit_tool_config("t1")
    hit = next(i for i in resp["issues"] if i["category"] == "empty_parameters")
    assert hit.get("fix_available") is False
    assert not hit.get("fix")
    assert "假" in (hit.get("suggestion") or "") or "占位" in (hit.get("suggestion") or "")


@pytest.mark.asyncio
async def test_mcp_audit_missing_url_has_no_placeholder_fix(monkeypatch, tmp_path):
    """Missing MCP url must not one-click fill 127.0.0.1:8080."""
    class _Srv:
        name = "m1"
        transport = "sse"
        url = ""
        command = ""
        allowed_tools = ["t"]
        description = "d"
        metadata = {"display_name": "m1", "description": "d"}

    class _Mgr:
        def get_server(self, name):
            return _Srv() if name == "m1" else None

    monkeypatch.setattr(
        "core.api.routers.mcp_admin._workspace_mcp_manager",
        lambda: _Mgr(),
    )
    # Ensure no server.yaml so runtime branch is used
    monkeypatch.setattr(
        "pathlib.Path.home",
        lambda: tmp_path,
    )

    from core.api.routers.mcp_admin import audit_mcp_server_config

    resp = await audit_mcp_server_config("m1")
    hit = next(i for i in resp["issues"] if i["category"] == "missing_url")
    assert hit.get("fix_available") is False
    assert not hit.get("fix")


@pytest.mark.asyncio
async def test_workflow_structure_audit_detects_cycle_and_missing_agent(monkeypatch):
    # Workspace root (…/aiPlatform), not aiPlat-core
    root = Path(__file__).resolve().parents[5]
    plat = str(root / "aiPlat-platform")
    if plat not in sys.path:
        sys.path.insert(0, plat)

    from api.routers import workflows as wf_mod

    class _Svc:
        async def get(self, wid):
            return {
                "id": wid,
                "name": "wf",
                "description": "d",
                "nodes": [
                    {
                        "id": "a",
                        "type": "stageNode",
                        "data": {
                            "type": "agent",
                            "label": "A",
                            "config": {"agentId": ""},
                        },
                    },
                    {
                        "id": "b",
                        "type": "stageNode",
                        "data": {"type": "http", "label": "H", "config": {"url": ""}},
                    },
                ],
                "edges": [
                    {"source": "a", "target": "b"},
                    {"source": "b", "target": "a"},
                ],
            }

    monkeypatch.setattr(wf_mod, "_svc", _Svc())
    resp = await wf_mod.audit_workflow_endpoint("w1", _auth="ok")
    cats = {i["category"] for i in resp["issues"]}
    assert "missing_agent_id" in cats
    assert "missing_http_url" in cats
    assert "cycle_detected" in cats


def _stub_model_audit(monkeypatch):
    monkeypatch.setattr(
        "core.apps.tools.base.get_tool_registry",
        lambda: type("R", (), {"list_tools": lambda self: []})(),
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection.best_model_for_purpose_with_meta",
        lambda purpose, messages=None: {
            "model": "qwen2.5:7b",
            "model_tier": "medium",
            "model_purpose": purpose,
        },
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection._load_llm_profile",
        lambda: {"purpose_profiles": {"agent": {}, "chat": {}}},
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection._get_cached_model_manager",
        lambda: type(
            "M",
            (),
            {
                "select": lambda self, **k: None,
                "get_model_tier": lambda self, *a, **k: "unknown",
            },
        )(),
    )


@pytest.mark.asyncio
async def test_audit_listed_mcp_emits_binding_ok(tmp_path, monkeypatch):
    home = tmp_path / ".aiplat"
    agent_dir = home / "agents" / "audit_mcp_ok"
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text(
        "---\n"
        "name: audit_mcp_ok\n"
        "agent_type: react\n"
        "status: ready\n"
        "mcp_servers:\n"
        "  - good_mcp\n"
        "loop_type: react\n"
        "toolset: workspace_default\n"
        "permissions:\n"
        "  - llm:generate\n"
        "config:\n"
        "  system_prompt: you are a test agent\n"
        "---\n"
        "## Persona\n"
        "test\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    _stub_model_audit(monkeypatch)

    class _Srv:
        status = "listed"
        enabled = True

    class _Mgr:
        def get_server(self, name):
            return _Srv() if name == "good_mcp" else None

    monkeypatch.setattr(
        "core.management.mcp_manager.MCPManager",
        lambda scope="workspace": _Mgr(),
    )

    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_mcp_ok")
    cats = {i["category"] for i in resp.issues}
    assert "mcp_not_listed" not in cats
    assert "invalid_mcp" not in cats
    assert "mcp_binding_ok" in cats
    hit = next(i for i in resp.issues if i["category"] == "mcp_binding_ok")
    assert hit["severity"] == "info"
    assert "good_mcp" in str(hit.get("current") or "")


@pytest.mark.asyncio
async def test_audit_unlisted_mcp_no_binding_ok(tmp_path, monkeypatch):
    home = tmp_path / ".aiplat"
    agent_dir = home / "agents" / "audit_mcp_draft"
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text(
        "---\n"
        "name: audit_mcp_draft\n"
        "agent_type: react\n"
        "status: ready\n"
        "mcp_servers:\n"
        "  - draft_mcp\n"
        "loop_type: react\n"
        "toolset: workspace_default\n"
        "permissions:\n"
        "  - llm:generate\n"
        "config:\n"
        "  system_prompt: you are a test agent\n"
        "---\n"
        "## Persona\n"
        "test\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    _stub_model_audit(monkeypatch)

    class _Srv:
        status = "draft"
        enabled = True

    class _Mgr:
        def get_server(self, name):
            return _Srv() if name == "draft_mcp" else None

    monkeypatch.setattr(
        "core.management.mcp_manager.MCPManager",
        lambda scope="workspace": _Mgr(),
    )

    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_mcp_draft")
    cats = {i["category"] for i in resp.issues}
    assert "mcp_not_listed" in cats
    assert "mcp_binding_ok" not in cats


@pytest.mark.asyncio
async def test_audit_listed_sub_agent_and_workflow_binding_ok(tmp_path, monkeypatch):
    home = tmp_path / ".aiplat"
    agent_dir = home / "agents" / "audit_bind_ok"
    agent_dir.mkdir(parents=True)
    sub_dir = home / "agents" / "child_listed"
    sub_dir.mkdir(parents=True)
    (sub_dir / "AGENT.md").write_text(
        "---\nname: child_listed\nagent_type: react\nstatus: listed\n---\n# child\n",
        encoding="utf-8",
    )
    wf_dir = home / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "demo_flow.json").write_text("{}", encoding="utf-8")
    (agent_dir / "AGENT.md").write_text(
        "---\n"
        "name: audit_bind_ok\n"
        "agent_type: react\n"
        "status: ready\n"
        "agent_ids:\n"
        "  - child_listed\n"
        "workflows:\n"
        "  - demo_flow\n"
        "loop_type: react\n"
        "toolset: workspace_default\n"
        "permissions:\n"
        "  - llm:generate\n"
        "config:\n"
        "  system_prompt: you are a test agent\n"
        "---\n"
        "## Persona\n"
        "test\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    _stub_model_audit(monkeypatch)

    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_bind_ok")
    cats = {i["category"] for i in resp.issues}
    assert "sub_agent_not_listed" not in cats
    assert "workflow_not_listed" not in cats
    assert "sub_agent_binding_ok" in cats
    assert "workflow_binding_ok" in cats
    assert "child_listed" in next(
        i["current"] for i in resp.issues if i["category"] == "sub_agent_binding_ok"
    )
    assert "demo_flow" in next(
        i["current"] for i in resp.issues if i["category"] == "workflow_binding_ok"
    )