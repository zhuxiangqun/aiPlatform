"""Phase C: Tool three paths + MCP connection lifecycle honesty."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core.harness.maintenance.asset_compat import (
    TIER_CONNECTABLE,
    TIER_CONNECTED,
    TIER_GATED,
    TIER_MAPPED,
    TIER_NEEDS_IMPL,
    TIER_SCHEMA_ONLY,
    enable_tool_impl_draft,
    finalize_mcp_compat,
    finalize_tool_compat,
    is_mcp_schedulable,
    is_tool_schedulable,
    mark_mcp_connection,
    mcp_schedulable_error,
    tool_schedulable_error,
    write_tool_impl_draft,
)


def test_tool_mapped_live_py(tmp_path: Path):
    py = tmp_path / "echo.py"
    py.write_text("TOOL_DEF={'name':'echo','execute':lambda p:{}}\n", encoding="utf-8")
    c = finalize_tool_compat(py, adapt_summary={"adapted": True, "pattern": "workspace_create"})
    assert c["tier"] == TIER_MAPPED
    assert c["schedulable"] is True
    assert c["ui_state"] == "现在就能用"
    assert is_tool_schedulable(py) is True


def test_tool_needs_impl_draft_only(tmp_path: Path):
    py = tmp_path / "drafty.py"
    write_tool_impl_draft(py, "TOOL_DEF={'name':'drafty','execute':lambda p:{}}\n")
    c = finalize_tool_compat(py, adapt_summary={"adapted": True, "pattern": "import_draft"})
    assert c["tier"] == TIER_NEEDS_IMPL
    assert c["schedulable"] is False
    assert c["ui_state"] == "还差几步"
    assert is_tool_schedulable(py) is False
    err = tool_schedulable_error(py, tool_id="drafty")
    assert err["error"] == "tool_not_schedulable"


def test_tool_enable_impl_draft(tmp_path: Path):
    py = tmp_path / "promo.py"
    code = "TOOL_DEF={'name':'promo','execute':lambda p:{'ok':True}}\n"
    write_tool_impl_draft(py, code)
    finalize_tool_compat(py, adapt_summary={"adapted": True, "pattern": "import_draft"})
    res = enable_tool_impl_draft(py)
    assert res["ok"] is True
    assert py.is_file()
    assert res["tier"] == TIER_MAPPED
    assert is_tool_schedulable(py) is True


def test_tool_schema_only(tmp_path: Path):
    py = tmp_path / "schema_tool.py"
    (tmp_path / "schema_tool.schema.json").write_text('{"type":"object"}\n', encoding="utf-8")
    c = finalize_tool_compat(py)
    assert c["tier"] == TIER_SCHEMA_ONLY
    assert c["schedulable"] is False
    assert c["ui_state"] == "不能用"


def test_tool_fail_open_missing_compat(tmp_path: Path):
    py = tmp_path / "legacy.py"
    py.write_text("x=1\n", encoding="utf-8")
    assert is_tool_schedulable(py) is True  # no COMPAT → fail-open


def test_mcp_connectable_then_connected(tmp_path: Path):
    d = tmp_path / "svc"
    d.mkdir()
    (d / "server.yaml").write_text(
        "name: svc\nenabled: true\ntransport: sse\nurl: http://127.0.0.1:9\n",
        encoding="utf-8",
    )
    c0 = finalize_mcp_compat(d, connection_status="connectable")
    assert c0["tier"] == TIER_CONNECTABLE
    assert c0["schedulable"] is False
    assert is_mcp_schedulable(d) is False

    c1 = mark_mcp_connection(d, "connected")
    assert c1["tier"] == TIER_CONNECTED
    assert c1["schedulable"] is True
    assert c1["ui_state"] == "现在就能用"

    c2 = mark_mcp_connection(d, "connectable")  # disconnect honesty
    assert c2["tier"] == TIER_CONNECTABLE
    assert c2["schedulable"] is False
    err = mcp_schedulable_error(d, mcp_id="svc")
    assert err["error"] == "mcp_not_schedulable"


def test_mcp_gated_high_risk(tmp_path: Path):
    d = tmp_path / "risky"
    d.mkdir()
    (d / "server.yaml").write_text("name: risky\nenabled: true\ntransport: stdio\n", encoding="utf-8")
    (d / "policy.yaml").write_text("risk_level: high\napproval_required: true\n", encoding="utf-8")
    c = finalize_mcp_compat(d, connection_status="connected")
    assert c["tier"] == TIER_GATED
    assert c["schedulable"] is True


def test_mcp_fail_open_missing_compat(tmp_path: Path):
    d = tmp_path / "legacy-mcp"
    d.mkdir()
    (d / "server.yaml").write_text("name: legacy-mcp\n", encoding="utf-8")
    assert is_mcp_schedulable(d) is True


@pytest.mark.asyncio
async def test_sys_tool_call_denies_needs_impl(tmp_path: Path, monkeypatch):
    from core.harness.interfaces.tool import ToolResult
    from core.harness.syscalls.tool import sys_tool_call

    py = tmp_path / "blocked_call.py"
    write_tool_impl_draft(py, "TOOL_DEF={'name':'blocked_call'}\n")
    finalize_tool_compat(py, adapt_summary={"adapted": True, "pattern": "import_draft"})

    tool = SimpleNamespace(
        name="blocked_call",
        _config=SimpleNamespace(metadata={"provenance": {"scope": "workspace", "tool_path": str(py)}}),
    )
    # Avoid ControlProfile / TraceGate side effects by ensuring compat gate runs first
    out = await sys_tool_call(tool, {})
    assert isinstance(out, ToolResult)
    assert out.success is False
    assert out.error == "tool_not_schedulable"
