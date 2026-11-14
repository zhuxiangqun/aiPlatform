"""
DI Factory - 依赖注入容器工厂函数

文档位置：docs/di/index.md
"""

from typing import Optional

from .container import DIContainer
from .container import DIContainerImpl
from .schemas import DIContainerConfig


def create_container(config: Optional[DIContainerConfig] = None) -> DIContainer:
    """创建 DI 容器。

    Args:
        config: config 参数。
    """
    return DIContainerImpl(config)


def get_container() -> DIContainer:
    """
    获取全局 DI 容器（单例）

    返回：
        全局 DIContainer 实例
    """
    global _global_container
    if _global_container is None:
        _global_container = create_container()
    return _global_container


# 全局容器实例
_global_container: Optional[DIContainer] = None
