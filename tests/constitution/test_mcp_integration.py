"""
§45: MCP Integration Smoke Test

Tests that the MCP test-invoke endpoint actually works by spawning
the local_tools_server process and verifying the JSON-RPC protocol.

This test targets the LOCAL stdio MCP server path — it does NOT require
a running FastAPI server, only that the core module is importable.
"""

import asyncio
import json
import pytest


ASYNC_SLEEP_TIME = 0  # track for async guard


async def _send_and_recv(proc, request: dict, timeout: float = 10) -> dict:
    """Send a JSON-RPC request and read the response."""
    proc.stdin.write((json.dumps(request) + "\n").encode("utf-8"))
    await proc.stdin.drain()
    line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
    return json.loads(line.decode("utf-8"))


@pytest.mark.asyncio
async def test_mcp_smoke_initialize():
    """Verify MCP server starts and responds to initialize."""
    import sys

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "core.apps.mcp.local_tools_server",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        resp = await _send_and_recv(proc, {
            "jsonrpc": "2.0", "id": 0, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "smoke-test", "version": "1.0.0"},
            },
        })
        assert "result" in resp, f"initialize failed: {resp}"
        assert resp["result"]["protocolVersion"] == "2024-11-05"
        assert resp["result"]["serverInfo"]["name"] == "aiplat-local-tools"
    finally:
        proc.terminate()
        await asyncio.wait_for(proc.wait(), timeout=3)


@pytest.mark.asyncio
async def test_mcp_smoke_list_tools():
    """Verify tools/list returns at least the test-1 tool."""
    import sys

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "core.apps.mcp.local_tools_server",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        # Initialize
        await _send_and_recv(proc, {
            "jsonrpc": "2.0", "id": 0, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                       "clientInfo": {"name": "smoke-test", "version": "1.0.0"}},
        })
        # List tools
        resp = await _send_and_recv(proc, {
            "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {},
        })
        assert "result" in resp, f"tools/list failed: {resp}"
        tools = resp["result"].get("tools", [])
        tool_names = [t["name"] for t in tools]
        assert "test-1" in tool_names, f"test-1 tool not found in {tool_names}"
        assert "api_test" in tool_names, f"api_test tool not found in {tool_names}"
        assert "square_calc" in tool_names, f"square_calc tool not found in {tool_names}"
    finally:
        proc.terminate()
        await asyncio.wait_for(proc.wait(), timeout=3)


@pytest.mark.asyncio
async def test_mcp_smoke_call_tool_test_1():
    """Verify tools/call with test-1 returns correct result (num=11 → 121)."""
    import sys

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "core.apps.mcp.local_tools_server",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        # Initialize
        await _send_and_recv(proc, {
            "jsonrpc": "2.0", "id": 0, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                       "clientInfo": {"name": "smoke-test", "version": "1.0.0"}},
        })
        # Call tool
        resp = await _send_and_recv(proc, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "test-1", "arguments": {"num": 11}},
        })
        assert "result" in resp, f"tools/call failed: {resp}"
        content = resp["result"].get("content", [])
        assert len(content) > 0, "empty content in response"
        text = content[0].get("text", "")
        result_obj = json.loads(text)
        assert result_obj.get("result") == 121, f"expected 121, got {result_obj}"
    finally:
        proc.terminate()
        await asyncio.wait_for(proc.wait(), timeout=3)


@pytest.mark.asyncio
async def test_mcp_smoke_uses_sys_executable():
    """Verify the MCP server spawn uses sys.executable (not bare python3).

    In CI, sys.executable must be from a venv/virtualenv.
    Locally, warn but don't fail — developer may use system Python for quick tests.
    """
    import os
    import sys
    assert sys.executable, "sys.executable must be defined"

    is_venv = ".venv" in sys.executable or "virtualenv" in sys.executable.lower()
    in_ci = os.getenv("CI") or os.getenv("GITHUB_ACTIONS") or os.getenv("AIPLAT_CI")

    if in_ci and not is_venv:
        pytest.fail(
            f"CI requires venv Python for MCP smoke tests, got: {sys.executable}"
        )
    elif not is_venv:
        pytest.skip(
            f"Skipping venv check: local run with {sys.executable}"
        )
