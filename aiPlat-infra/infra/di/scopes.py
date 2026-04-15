"""
DI Scopes - 作用域管理

文档位置：docs/di/index.md
"""

from typing import Dict, Optional

from .schemas import Lifetime, ScopeConfig


class ScopeManager:
    """
    作用域管理器

    管理预定义作用域配置
    """

    DEFAULT_SCOPES = {
        "global": ScopeConfig(name="global", lifetime=Lifetime.SINGLETON),
        "request": ScopeConfig(name="request", lifetime=Lifetime.SCOPED),
        "session": ScopeConfig(name="session", lifetime=Lifetime.SCOPED),
        "transient": ScopeConfig(name="transient", lifetime=Lifetime.TRANSIENT),
    }

    def __init__(self):
        self._scopes: Dict[str, ScopeConfig] = self.DEFAULT_SCOPES.copy()

    def register_scope(self, config: ScopeConfig) -> None:
        """注册作用域"""
        self._scopes[config.name] = config

    def get_scope(self, name: str) -> Optional[ScopeConfig]:
        """获取作用域配置"""
        return self._scopes.get(name)

    def list_scopes(self) -> Dict[str, ScopeConfig]:
        """列出所有作用域"""
        return self._scopes.copy()

    def has_scope(self, name: str) -> bool:
        """检查作用域是否存在"""
        return name in self._scopes
