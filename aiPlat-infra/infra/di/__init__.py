"""
DI Module - 依赖注入容器

提供轻量级依赖注入容器，用于 infra 层内部模块之间的依赖管理

文档位置：docs/di/index.md

文件结构：
├── __init__.py              # 模块导出
├── container.py             # DIContainer 接口
├── factory.py               # create_container()
├── schemas.py               # 数据模型
├── scopes.py                # 作用域管理
├── interceptors.py          # 拦截器
└── registries.py            # 服务注册表

注意：此 DI 容器用于 infra 内部模块之间的依赖管理。
与框架级 DI（如 FastAPI）不冲突。
"""

from .container import DIContainer, DIContainerImpl
from .factory import create_container
from .schemas import (
    DIContainerConfig,
    ServiceDescriptor,
    Lifetime,
)

__all__ = [
    "DIContainer",
    "DIContainerImpl",
    "create_container",
    "DIContainerConfig",
    "ServiceDescriptor",
    "Lifetime",
]
