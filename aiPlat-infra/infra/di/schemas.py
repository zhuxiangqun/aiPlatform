"""
DI Schemas - 依赖注入数据模型定义
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type


class Lifetime(Enum):
    """服务生命周期"""

    TRANSIENT = "transient"  # 每次请求新实例
    SCOPED = "scoped"  # 作用域内单例
    SINGLETON = "singleton"  # 全局单例


@dataclass
class ServiceDescriptor:
    """服务描述符"""

    service: Type  # 服务类型
    implementation: Type  # 实现类型
    lifetime: Lifetime = Lifetime.SINGLETON
    factory: Optional[Callable] = None
    instance: Optional[Any] = None


@dataclass
class DIContainerConfig:
    """DI容器配置"""

    auto_wire: bool = True
    scan_packages: List[str] = field(default_factory=list)
    strict_mode: bool = False
    default_singleton: bool = True
    default_lazy: bool = True


@dataclass
class ScopeConfig:
    """作用域配置"""

    name: str
    lifetime: Lifetime = Lifetime.SCOPED


@dataclass
class InterceptorConfig:
    """拦截器配置"""

    name: str
    enabled: bool = True
    order: int = 0
