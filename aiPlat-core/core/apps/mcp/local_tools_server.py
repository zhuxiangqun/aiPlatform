"""MCP stdio server — exposes ~/.aiplat/tools/ workspace tools via JSON-RPC 2.0.

Usage (standalone):
    python -m core.apps.mcp.local_tools_server

Usage (via aiPlat MCP management):
    Create MCP server config with:
      transport: stdio
      command: /path/to/.venv/bin/python
      args: ["-m", "core.apps.mcp.local_tools_server"]

Protocol:
    One JSON-RPC request per stdin line, one JSON-RPC response per stdout line.
    Supported methods: initialize, tools/list, tools/call
"""

from __future__ import annotations
import logging

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _scan_tools() -> List[Dict[str, Any]]:
    """Scan ~/.aiplat/tools/ for TOOL_DEF exports."""
    tools: List[Dict[str, Any]] = []
    tools_dir = Path(os.environ.get("AIPLAT_TOOLS_PATH", Path.home() / ".aiplat" / "tools"))
    if not tools_dir.is_dir():
        return tools

    for fpath in sorted(tools_dir.glob("*.py")):
        try:
            mod_name = f"mcp_tool_{fpath.stem.replace('-', '_')}"
            spec = importlib.util.spec_from_file_location(mod_name, str(fpath))
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            td = getattr(mod, "TOOL_DEF", None)
            if td and isinstance(td, dict):
                tools.append({
                    "name": td.get("name", fpath.stem),
                    "description": td.get("description", ""),
                    "inputSchema": td.get("parameters", {"type": "object", "properties": {}}),
                    "_execute_fn": td.get("execute"),
                    "_file": str(fpath),
                })
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    return tools


def _format_tool_list(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Format tool list for MCP tools/list response."""
    result = []
    for t in tools:
        entry: Dict[str, Any] = {
            "name": t["name"],
            "description": t["description"],
        }
        input_schema = t.get("inputSchema", {})
        if isinstance(input_schema, dict) and input_schema:
            entry["inputSchema"] = input_schema
        result.append(entry)
    return result


def _call_tool(tools: List[Dict[str, Any]], name: str, arguments: Dict[str, Any]) -> Any:
    """Call a tool by name with arguments."""
    for t in tools:
        if t["name"] == name:
            fn = t.get("_execute_fn")
            if fn is None:
                return {"isError": True, "content": [{"type": "text", "text": f"Tool '{name}' has no execute function"}]}
            try:
                result = fn(arguments)
                return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
            except Exception as e:
                return {"isError": True, "content": [{"type": "text", "text": f"Tool error: {str(e)}"}]}

    return {"isError": True, "content": [{"type": "text", "text": f"Tool '{name}' not found"}], "data": {"available_tools": [t["name"] for t in tools]}}


def _send(data: Dict[str, Any]) -> None:
    """Write a JSON-RPC message to stdout."""
    line = json.dumps(data, ensure_ascii=False) + "\n"
    sys.stdout.write(line)
    sys.stdout.flush()


def _error(req_id: Any, code: int, message: str) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def main() -> None:
    # Pre-scan tools at startup so first tools/list is fast
    tools = _scan_tools()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {}) or {}

        # --- initialize ---
        if method == "initialize":
            _send({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "aiplat-local-tools",
                        "version": "0.1.0",
                    },
                },
            })

        # --- tools/list ---
        elif method == "tools/list":
            _send({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": _format_tool_list(tools)},
            })

        # --- tools/call ---
        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {}) or {}
            result = _call_tool(tools, tool_name, arguments)
            _send({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": result,
            })

        # --- ping ---
        elif method == "ping":
            _send({"jsonrpc": "2.0", "id": req_id, "result": {}})

        # --- unknown ---
        elif req_id is not None:
            _error(req_id, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    main()
