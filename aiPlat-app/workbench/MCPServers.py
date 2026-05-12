"""
MCPServers — MCP Server 管理前端页面组件。

面向终端用户：管理已注册的 MCP Server 列表，
查看每个 Server 暴露的工具，启用/禁用 Server。
"""

from typing import Any


class MCPServers:
    def __init__(self):
        self.title = "MCP Servers"
        self.description = "Manage Model Context Protocol servers and their tools"

    def render_server_list(self, servers: list, scope: str = "workspace") -> Any:
        """渲染 MCP Server 列表。
        每个 Server 项显示：名称、URL、scope、状态（enabled/disabled）、
        已注册工具数量。
        """
        return {
            "servers": servers,
            "scope": scope,
            "actions": {
                "enable": "POST /api/v1/mcp/servers/{name}/enable",
                "disable": "POST /api/v1/mcp/servers/{name}/disable",
            },
        }

    def render_register_form(self) -> Any:
        """渲染注册新 MCP Server 的表单。
        输入：名称、URL（http/https）、scope（workspace/engine）。
        """
        return {
            "form": {
                "fields": ["name", "url", "scope"],
                "url_help": "Must start with http:// or https://",
                "scope_options": ["workspace", "engine"],
            },
            "endpoint": "POST /api/v1/mcp/servers",
        }

    def render_tool_list(self, server_name: str, tools: list) -> Any:
        """渲染某个 MCP Server 暴露的工具列表。
        每个工具显示：name、description、input_schema。
        """
        return {
            "server": server_name,
            "tools": tools,
            "endpoint": f"GET /api/v1/mcp/servers/{server_name}/tools",
        }

    def render_policy_check(self, server_name: str, result: dict) -> Any:
        """渲染 MCP Server 的策略合规性检查结果。"""
        return {
            "server": server_name,
            "policy_check": result,
            "endpoint": f"GET /api/v1/mcp/servers/{server_name}/policy-check",
        }
