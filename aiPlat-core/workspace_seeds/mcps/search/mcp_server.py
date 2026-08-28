#!/usr/bin/env python3
"""
MCP Search — Agent 搜索基础设施（AnySearch 借鉴 P1-1，2026-08-28）。

协议: JSON-RPC over stdio（对齐 workspace_seeds/mcps/* 种子 MCP 模式）。
能力:
  search_web      — Web 结构化搜索（信源标注事实条目，DuckDuckGo HTML/JSON 融合）
  search_routed   — 意图路由统一检索（code/knowledge/web 三通道分发）
  search_intent   — 意图判定（只返回路由结果，供 Agent 决策）

安全:
  - 只读检索，不修改系统状态
  - 无网络外带（结果仅经 stdio 返回调用方）
  - 可经 MCP_SEARCH_WEB_ENABLED=false 关闭 web 通道（隐私场景）
"""
import sys
import json
import os

# ═══ 配置 ═══
WEB_ENABLED = os.environ.get("MCP_SEARCH_WEB_ENABLED", "true").lower() != "false"
MAX_RESULTS = int(os.environ.get("MCP_SEARCH_MAX_RESULTS", "8"))
# ═══ ═══ ═══

TOOLS = [
    {
        "name": "search_web",
        "description": "Web 结构化搜索：返回信源标注事实条目（claim/source_title/source_url/evidence_snippet/confidence），"
                       "剔除广告/HTML 噪声，面向 Agent 机器推理。默认 DuckDuckGo 多后端融合去重。",
        "schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询词"},
                "limit": {"type": "integer", "description": "返回结果数量（默认 8，最大 20）"},
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_routed",
        "description": "意图路由统一检索：先判定查询意图（代码/内部知识/通用事实），自动路由到匹配通道，"
                       "返回结构化事实条目 + 信源标注。避免全域盲搜。",
        "schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索查询词"},
                "top_k": {"type": "integer", "description": "返回结果数量（默认 8，最大 20）"},
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_intent",
        "description": "意图判定：返回查询被路由到的通道（code/knowledge/web）及原因，供 Agent 决策是否继续检索。",
        "schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "查询词"},
            },
            "required": ["query"]
        }
    },
]


async def _handle_search_web(query: str, limit: int):
    """Web 结构化搜索（复用 WebSearchTool structured 模式）。"""
    try:
        from core.apps.tools.web.web_search import WebSearchTool
        tool = WebSearchTool()
        r = await tool.execute({"query": query, "limit": limit, "structured": True})
        results = r.get("results") or []
        return {"content": json.dumps({"success": r.get("success", True), "total": len(results),
                                       "results": results}, ensure_ascii=False)}
    except Exception as e:
        return {"content": json.dumps({"success": False, "error": str(e)[:300], "results": []},
                                      ensure_ascii=False), "is_error": True}


async def _handle_search_routed(query: str, top_k: int):
    """意图路由统一检索。"""
    try:
        from core.harness.syscalls.retrieval import sys_routed_retrieve
        r = await sys_routed_retrieve(query, top_k=top_k, include_web=WEB_ENABLED)
        return {"content": json.dumps(r, ensure_ascii=False)}
    except Exception as e:
        return {"content": json.dumps({"error": str(e)[:300], "route": None,
                                       "results": [], "sources": []}, ensure_ascii=False), "is_error": True}


async def _handle_search_intent(query: str):
    try:
        from core.harness.syscalls.retrieval import _route_intent
        route = _route_intent(query)
        return {"content": json.dumps({"route": route}, ensure_ascii=False)}
    except Exception as e:
        return {"content": json.dumps({"error": str(e)[:300]}, ensure_ascii=False), "is_error": True}


def handle_list_tools():
    return {"tools": TOOLS}


async def handle_call_tool(name: str, arguments: dict):
    try:
        if name == "search_web":
            if not WEB_ENABLED:
                return {"content": "web 通道已关闭（MCP_SEARCH_WEB_ENABLED=false）", "is_error": True}
            q = str(arguments.get("query", "")).strip()
            if not q:
                return {"content": "query 不能为空", "is_error": True}
            return await _handle_search_web(q, min(int(arguments.get("limit", MAX_RESULTS)), 20))
        elif name == "search_routed":
            q = str(arguments.get("query", "")).strip()
            if not q:
                return {"content": "query 不能为空", "is_error": True}
            return await _handle_search_routed(q, min(int(arguments.get("top_k", MAX_RESULTS)), 20))
        elif name == "search_intent":
            return await _handle_search_intent(str(arguments.get("query", "")).strip())
        return {"content": f"unknown tool: {name}", "is_error": True}
    except Exception as e:
        return {"content": str(e)[:300], "is_error": True}


def main():
    import asyncio
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        req_id = req.get("id")
        method = req.get("method")
        if method == "initialize":
            resp = {"jsonrpc": "2.0", "id": req_id,
                    "result": {"protocolVersion": "2024-11-05",
                               "capabilities": {"tools": {}}, "serverInfo": {"name": "aiplat-search", "version": "1.0.0"}}}
        elif method == "tools/list":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": handle_list_tools()}
        elif method == "tools/call":
            params = req.get("params") or {}
            result = asyncio.run(handle_call_tool(str(params.get("name", "")), params.get("arguments") or {}))
            resp = {"jsonrpc": "2.0", "id": req_id, "result": result}
        elif method == "ping":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
        elif method == "notifications/initialized":
            continue
        else:
            resp = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"method not found: {method}"}}
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    *[".."] * 6))  # workspace_seeds/mcps/search → aiPlat-core
    main()
