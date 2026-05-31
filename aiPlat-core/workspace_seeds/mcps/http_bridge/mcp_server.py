#!/usr/bin/env python3
"""
MCP HTTP Bridge Server — Agent 通过此工具调用任意 REST/HTTP API。

协议: JSON-RPC over stdio (MCP protocol)
修改: 设置下方的 BASE_URL 和 AUTH_HEADER 来连接你的 API。
"""
import sys, json, os

# ═══ 配置（修改这里） ═══
BASE_URL = os.environ.get("MCP_HTTP_BASE_URL", "https://api.example.com")
AUTH_HEADER = os.environ.get("MCP_HTTP_AUTH", "Bearer YOUR_TOKEN")
# ═══ ═══ ═══ ═══ ═══ ═══

TOOLS = [
    {
        "name": "http_get",
        "description": f"发送 GET 请求到 {BASE_URL}。path 是URL路径（如 /users），params 是查询参数字典。",
        "schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "请求路径"},
                "params": {"type": "object", "description": "查询参数"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "http_post",
        "description": f"发送 POST 请求到 {BASE_URL}。body 是 JSON 请求体。",
        "schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "请求路径"},
                "body": {"type": "object", "description": "JSON 请求体"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "http_put",
        "description": f"发送 PUT 请求到 {BASE_URL}。",
        "schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "请求路径"},
                "body": {"type": "object", "description": "JSON 请求体"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "http_delete",
        "description": f"发送 DELETE 请求到 {BASE_URL}。",
        "schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "请求路径"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "http_patch",
        "description": f"发送 PATCH 请求到 {BASE_URL}（部分更新）。",
        "schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "请求路径"},
                "body": {"type": "object", "description": "JSON 请求体"}
            },
            "required": ["path"]
        }
    },
]


def _do_request(method: str, path: str, body: dict = None, params: dict = None):
    import urllib.request
    import urllib.error

    url = BASE_URL.rstrip("/") + "/" + path.lstrip("/")
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())

    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", AUTH_HEADER)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {
                "status": resp.status,
                "body": resp.read().decode("utf-8", errors="replace")[:10000]
            }
    except urllib.error.HTTPError as e:
        return {"status": e.code, "error": e.read().decode("utf-8", errors="replace")[:2000]}
    except Exception as e:
        return {"status": 0, "error": str(e)[:500]}


def handle_list_tools():
    return {"tools": TOOLS}

def handle_call_tool(name: str, arguments: dict):
    method_map = {
        "http_get": "GET",
        "http_post": "POST",
        "http_put": "PUT",
        "http_delete": "DELETE",
        "http_patch": "PATCH",
    }
    method = method_map.get(name)
    if not method:
        return {"content": "Unknown tool: " + name, "is_error": True}

    try:
        result = _do_request(method, arguments.get("path", "/"),
                             body=arguments.get("body"),
                             params=arguments.get("params"))
        return {"content": json.dumps(result, ensure_ascii=False, indent=2)}
    except Exception as e:
        return {"content": str(e), "is_error": True}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = req.get("method", "")
        req_id = req.get("id")

        if method == "list_tools":
            resp = handle_list_tools()
        elif method == "call_tool":
            params = req.get("params", {})
            resp = handle_call_tool(params.get("name", ""), params.get("arguments", {}))
        else:
            resp = {"error": "Unknown method: " + method}

        out = {"jsonrpc": "2.0", "id": req_id, "result": resp}
        print(json.dumps(out, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
