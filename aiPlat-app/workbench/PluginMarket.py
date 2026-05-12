"""
PluginMarket — Plugin 市场前端页面组件。

面向终端用户：浏览已安装插件、安装新插件、查看插件详情。
"""

from typing import Any


class PluginMarket:
    def __init__(self):
        self.title = "Plugin Market"
        self.description = "Browse, install, and manage AI plugins"

    def render_plugin_list(self, plugins: list) -> Any:
        """渲染已安装插件列表。
        每个插件项显示：名称、版本、状态（active/disabled/stale）、
        安装日期、risk_level、权限声明。
        """
        return {
            "plugins": plugins,
            "actions": {
                "enable": "POST /api/v1/plugins/{id}/enable",
                "disable": "POST /api/v1/plugins/{id}/disable",
                "rollback": "POST /api/v1/plugins/{id}/rollback",
            },
        }

    def render_install_form(self) -> Any:
        """渲染安装新 Plugin 的表单。
        支持输入来源 URL 或上传 manifest 文件（含 skills/tools/mcp_servers）。
        安装前平台层（PluginValidator）会校验 manifest 完整性。
        """
        return {
            "form": {
                "source_type": ["url", "upload"],
                "url_placeholder": "https://github.com/user/repo",
                "upload_accept": ".json,.yaml,.yml",
            },
            "endpoint": "PUT /api/v1/plugins",
        }

    def render_detail(self, plugin: dict) -> Any:
        """渲染 Plugin 详情侧栏：metadata、permissions、effects、changelog、版本历史。"""
        return {
            "plugin": plugin,
            "sections": [
                "metadata",
                "permissions",
                "effects",
                "versions",
                "changelog",
            ],
            "endpoints": {
                "versions": "GET /api/v1/plugins/{id}/versions",
                "rollback": "POST /api/v1/plugins/{id}/rollback",
            },
        }
