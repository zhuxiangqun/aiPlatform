#!/usr/bin/env python3
"""
MCP Shell Executor — Agent 通过此工具安全执行本地 shell 命令。

协议: JSON-RPC over stdio
安全: 每个允许的命令自动生成一个工具描述，Agent 可以直接看到可用命令列表。
       每个命令独立暴露为 mcp.shell_executor.<命令名>。
"""
import sys, json, os, subprocess

# ═══ 配置 ═══
SAFE_DIR = os.environ.get("MCP_SHELL_SAFE_DIR", "/tmp")
ALLOWED_CMDS = [c.strip() for c in os.environ.get("MCP_SHELL_ALLOWED", "ls,cat,grep,wc,head,tail,find,echo,pwd,date,whoami,df,du,ps,curl").split(",") if c.strip()]
TIMEOUT = int(os.environ.get("MCP_SHELL_TIMEOUT", "30"))
# ═══ ═══ ═══

# Common command descriptions so Agent knows when to use each one
CMD_DESCRIPTIONS = {
    "ls":       "列出目录内容。参数: 目录路径（可选）。",
    "cat":      "读取文本文件内容。参数: 文件路径。",
    "grep":     "在文件中搜索匹配的文本。参数: 模式 文件路径。",
    "wc":       "统计文件的行数、词数、字符数。参数: 文件路径。",
    "head":     "显示文件前 N 行（默认 10 行）。参数: 文件路径。",
    "tail":     "显示文件最后 N 行（默认 10 行）。参数: 文件路径。",
    "find":     "递归搜索文件/目录。参数: 路径 条件...。",
    "echo":     "打印指定文本。参数: 要打印的文本...。",
    "pwd":      "显示当前工作目录。无参数。",
    "date":     "显示或设置系统日期和时间。参数: 格式（可选）。",
    "whoami":   "显示当前用户名。无参数。",
    "df":       "显示磁盘剩余空间。参数: 路径（可选）。",
    "du":       "估算目录/文件的磁盘占用。参数: 路径。",
    "ps":       "查看当前运行的进程。参数: 选项（可选）。",
    "curl":     "发送 HTTP 请求获取 URL 内容。参数: URL 选项...。",
}


def _build_tools():
    tools = []
    for cmd in ALLOWED_CMDS:
        desc = CMD_DESCRIPTIONS.get(cmd, f"执行 {cmd} 命令。参数由空格分隔的字符串组成。")
        tools.append({
            "name": cmd,
            "description": f"[{cmd}] {desc} 工作目录: {SAFE_DIR}。超时: {TIMEOUT}s。",
            "schema": {
                "type": "object",
                "properties": {
                    "args": {
                        "type": "string",
                        "description": f"传给 {cmd} 的参数，空格分隔。如要列出 /tmp 下的 .log 文件: 'ls /tmp/*.log'。留空则不传参数。"
                    }
                },
                "required": []
            }
        })
    return tools


TOOLS = _build_tools()


def handle_list_tools():
    return {"tools": TOOLS}


def handle_call_tool(name: str, arguments: dict):
    if name not in ALLOWED_CMDS:
        return {"content": f"Command not allowed: {name}. Available: {', '.join(sorted(ALLOWED_CMDS))}", "is_error": True}

    args_str = (arguments.get("args") or "").strip()
    parts = [name] + (args_str.split() if args_str else [])

    try:
        result = subprocess.run(
            parts,
            capture_output=True, text=True, timeout=TIMEOUT,
            cwd=SAFE_DIR, env={**os.environ, "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        )
        output = result.stdout[:5000]
        if result.stderr:
            output += "\n[stderr]\n" + result.stderr[:2000]
        return {"content": output or f"(exit code {result.returncode})"}
    except subprocess.TimeoutExpired:
        return {"content": f"Command timed out after {TIMEOUT}s", "is_error": True}
    except FileNotFoundError:
        return {"content": f"Command not found: {name}", "is_error": True}
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
