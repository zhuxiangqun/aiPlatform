"""
DI Factory - 依赖注入容器工厂函数

文档位置：docs/di/index.md
"""

from typing import Optional

from .container import DIContainer
from .container import DIContainerImpl
from .schemas import DIContainerConfig


def create_container(config: Optional[DIContainerConfig] = None) -> DIContainer:
    """
    创建 DI 容器

    参数：
        config: 容器配置（可选）
            - auto_wire: 自动注入
            - scan_packages: 扫描包
            - strict_mode: 严格模式
            - default_singleton: 默认单例
            - default_lazy: 延迟初始化

    返回：
        DIContainer 实例

    示例：
        # 使用默认配置
        container = create_container()

        # 注册服务
        container.register(IDatabaseClient, PostgresClient, Lifetime.SINGLETON)

        # 解析服务
        db = container.resolve(IDatabaseClient)

        # 使用作用域
        with container.scope("request") as scope:
            service = scope.resolve(IService)
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
