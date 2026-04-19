"""
Workbench Client - Web UI Client

Web 管理界面的前端组件（React 组件占位）。
"""


class WorkbenchClient:
    """工作台客户端"""

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self._components: dict = {}

    def register_component(self, name: str, component: Any) -> None:
        """注册组件"""
        self._components[name] = component

    def render(self, component_name: str) -> Any:
        """渲染组件"""
        return self._components.get(component_name)

    def get_routes(self) -> list[dict]:
        """获取路由配置"""
        return [
            {"path": "/", "component": "Dashboard"},
            {"path": "/agents", "component": "AgentList"},
            {"path": "/skills", "component": "SkillList"},
            {"path": "/sessions", "component": "SessionList"},
            {"path": "/settings", "component": "Settings"},
        ]


workbench_client = WorkbenchClient()