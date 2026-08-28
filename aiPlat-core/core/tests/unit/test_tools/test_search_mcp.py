"""test_search_mcp.py — 搜索 MCP server 测试（AnySearch 借鉴 P1-1，2026-08-28）。

覆盖：① tools/list 协议返回 search_web/search_routed/search_intent 三工具
② initialize 握手 ③ search_intent 意图判定 ④ unknown method 错误响应。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "workspace_seeds" / "mcps" / "search"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import mcp_server  # noqa: E402


def _resp(req: dict):
    """模拟单请求 stdio 处理（直接调用 main 逻辑不可行 → 走 handle 函数）。"""
    req_id = req.get("id")
    method = req.get("method")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id,
                "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                           "serverInfo": {"name": "aiplat-search", "version": "1.0.0"}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": mcp_server.handle_list_tools()}
    if method == "tools/call":
        params = req.get("params") or {}
        import asyncio
        result = asyncio.run(mcp_server.handle_call_tool(str(params.get("name", "")),
                                                         params.get("arguments") or {}))
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def test_initialize_handshake():
    r = _resp({"id": 1, "method": "initialize"})
    assert r["result"]["serverInfo"]["name"] == "aiplat-search"
    assert "tools" in r["result"]["capabilities"]


def test_tools_list_has_search_tools():
    r = _resp({"id": 2, "method": "tools/list"})
    names = [t["name"] for t in r["result"]["tools"]]
    assert "search_web" in names
    assert "search_routed" in names
    assert "search_intent" in names


def test_search_intent_tool():
    """search_intent → 意图判定（code 特征查询）。"""
    r = _resp({"id": 3, "method": "tools/call",
               "params": {"name": "search_intent", "arguments": {"query": "python 报错"}}})
    payload = json.loads(r["result"]["content"])
    assert payload["route"] == "code"


def test_unknown_method_error():
    r = _resp({"id": 4, "method": "unknown/xyz"})
    assert r["error"]["code"] == -32601


def test_search_web_requires_query():
    r = _resp({"id": 5, "method": "tools/call",
               "params": {"name": "search_web", "arguments": {}}})
    assert "query 不能为空" in r["result"]["content"]
