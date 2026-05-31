#!/usr/bin/env python3
"""
MCP File Operations — Agent 通过此工具安全读写本地文件。

协议: JSON-RPC over stdio
安全: 只允许在 ALLOWED_DIRS 范围内操作，文件大小限制 MAX_FILE_SIZE。
"""
import sys, json, os

# ═══ 配置 ═══
ALLOWED_DIRS = set(os.environ.get("MCP_FILE_DIRS", "/tmp").split(","))
MAX_FILE_SIZE = int(os.environ.get("MCP_FILE_MAX_SIZE", str(10 * 1024 * 1024)))
# ═══ ═══ ═══

TOOLS = [
    {
        "name": "file_read",
        "description": "读取文本文件内容。返回前 10000 字符。",
        "schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "file_write",
        "description": "写入文本内容到文件。会覆盖已有文件。",
        "schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "要写入的文本内容"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "file_list",
        "description": "列出目录内容。",
        "schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "file_exists",
        "description": "检查文件或目录是否存在。",
        "schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件或目录路径"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "file_delete",
        "description": "删除文件或空目录。需要确认路径在许可范围内。",
        "schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件或空目录路径"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "file_append",
        "description": "追加文本内容到文件末尾，不覆盖已有内容。",
        "schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "要追加的文本内容"}
            },
            "required": ["path", "content"]
        }
    },
]


def _check_path(path: str) -> str:
    abs_path = os.path.abspath(os.path.expanduser(path))
    for d in ALLOWED_DIRS:
        allow = os.path.abspath(os.path.expanduser(d))
        if abs_path.startswith(allow):
            return abs_path
    raise PermissionError(f"Path not allowed: {path}. Allowed dirs: {', '.join(sorted(ALLOWED_DIRS))}")


def handle_list_tools():
    return {"tools": TOOLS}

def handle_call_tool(name: str, arguments: dict):
    try:
        if name == "file_read":
            path = _check_path(arguments.get("path", ""))
            size = os.path.getsize(path)
            if size > MAX_FILE_SIZE:
                return {"content": f"File too large ({size} > {MAX_FILE_SIZE} bytes)", "is_error": True}
            with open(path, "r", encoding="utf-8") as f:
                content = f.read(10000)
            return {"content": content}

        elif name == "file_write":
            path = _check_path(arguments.get("path", ""))
            content = arguments.get("content", "")
            os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"content": f"Written {len(content)} bytes to {path}"}

        elif name == "file_list":
            path = _check_path(arguments.get("path", ""))
            if not os.path.isdir(path):
                return {"content": f"Not a directory: {path}", "is_error": True}
            items = []
            for entry in sorted(os.listdir(path)):
                full = os.path.join(path, entry)
                tag = "[D]" if os.path.isdir(full) else "[F]"
                size = os.path.getsize(full) if os.path.isfile(full) else 0
                items.append(f"{tag} {entry} ({size} bytes)")
            return {"content": "\n".join(items[:200]) or "(empty directory)"}

        elif name == "file_exists":
            path = _check_path(arguments.get("path", ""))
            return {"content": json.dumps({"exists": os.path.exists(path), "is_file": os.path.isfile(path), "is_dir": os.path.isdir(path)})}

        elif name == "file_delete":
            path = _check_path(arguments.get("path", ""))
            if not os.path.exists(path):
                return {"content": f"Not found: {path}", "is_error": True}
            if os.path.isdir(path):
                os.rmdir(path)  # only empty dirs
            else:
                os.remove(path)
            return {"content": f"Deleted {path}"}

        elif name == "file_append":
            path = _check_path(arguments.get("path", ""))
            content = arguments.get("content", "")
            os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(content)
            return {"content": f"Appended {len(content)} bytes to {path}"}

        else:
            return {"content": "Unknown tool: " + name, "is_error": True}

    except PermissionError as e:
        return {"content": str(e), "is_error": True}
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
