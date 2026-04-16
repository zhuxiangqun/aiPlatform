"""
DIContainer Implementation - 依赖注入容器实现

文档位置：docs/di/index.md
"""

from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional, Type

from .schemas import Lifetime, ServiceDescriptor, DIContainerConfig
from .base import DIContainer, IScope

import warnings
import importlib
import pkgutil
import logging

from .interceptors import (
    InterceptorChain,
    LoggingInterceptor,
    TimingInterceptor,
    CachingInterceptor,
    MetricsInterceptor,
    ErrorHandlingInterceptor,
    Proxy,
)
from .auto import list_injectables

warnings.filterwarnings("ignore", category=DeprecationWarning)


class _DummyLogger:
    """空日志记录器"""

    def debug(self, msg):
        pass

    def warning(self, msg):
        pass


_log = _DummyLogger()


class ScopeImpl(IScope):
    """作用域实现"""

    def __init__(self, container: "DIContainerImpl", name: str):
        self._container = container
        self._name = name
        self._instances: Dict[Type, Any] = {}

    def resolve(self, service: Type) -> Any:
        """解析服务"""
        # 检查是否有已创建的实例
        if service in self._instances:
            return self._instances[service]

        # 从容器获取实例
        instance = self._container._create_instance(service)

        # 如果是 scoped 生命周期，缓存实例
        desc = self._container._services.get(service)
        if desc and desc.lifetime == Lifetime.SCOPED:
            self._instances[service] = instance

        return self._container._wrap(instance)

    def close(self) -> None:
        """关闭作用域，清理资源"""
        for instance in self._instances.values():
            if hasattr(instance, "close"):
                try:
                    instance.close()
                except Exception:
                    pass
        self._instances.clear()
        _log.debug(f"Scope '{self._name}' closed")


class DIContainerImpl(DIContainer):
    """
    依赖注入容器实现

    支持：
    - 多种注册方式（类、实例、工厂）
    - 生命周期管理（TRANSIENT、SCOPED、SINGLETON）
    - 作用域（global、request、session）
    - 自动注入
    """

    def __init__(self, config: Optional[DIContainerConfig] = None):
        self._config = config or DIContainerConfig()
        self._services: Dict[Type, ServiceDescriptor] = {}
        self._singletons: Dict[Type, Any] = {}
        self._scopes: Dict[str, ScopeImpl] = {}
        self._logger = logging.getLogger("infra.di")
        self._interceptor_chain: Optional[InterceptorChain] = None
        self._interceptors: Dict[str, Any] = {}

        self._bootstrap_from_config()

    def _bootstrap_from_config(self) -> None:
        """Bootstrap container: scan_packages + build interceptors + auto-register injectables."""
        self._build_interceptors()
        self._scan_packages()
        self._register_injectables()

    def _build_interceptors(self) -> None:
        names = [str(n).strip().lower() for n in (self._config.interceptors or []) if str(n).strip()]
        if not names:
            self._interceptor_chain = None
            self._interceptors = {}
            return
        chain = InterceptorChain()
        for n in names:
            if n == "logging":
                inst = LoggingInterceptor(logger=self._logger)
            elif n == "timing":
                inst = TimingInterceptor()
            elif n == "caching":
                inst = CachingInterceptor()
            elif n == "metrics":
                inst = MetricsInterceptor()
            elif n in ("error_handling", "error", "errors"):
                inst = ErrorHandlingInterceptor(logger=self._logger)
            else:
                continue
            chain.add(inst)
            self._interceptors[n] = inst
        self._interceptor_chain = chain

    def get_interceptor(self, name: str) -> Optional[Any]:
        return self._interceptors.get((name or "").strip().lower())

    def _scan_packages(self) -> None:
        """Import configured packages and their submodules to trigger @injectable registrations."""
        for pkg_name in self._config.scan_packages or []:
            pkg_name = str(pkg_name).strip()
            if not pkg_name:
                continue
            try:
                pkg = importlib.import_module(pkg_name)
            except Exception as e:
                self._logger.warning(f"DI scan import failed for {pkg_name}: {e}")
                continue
            try:
                if hasattr(pkg, "__path__"):
                    for _, modname, _ in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
                        try:
                            importlib.import_module(modname)
                        except Exception:
                            continue
            except Exception:
                continue

    def _register_injectables(self) -> None:
        """Register injectable specs collected during module import."""
        for spec in list_injectables():
            try:
                self.register(spec.service, spec.implementation, lifetime=spec.lifetime)
            except Exception:
                continue

    def _wrap(self, instance: Any) -> Any:
        """Wrap instance with interceptors if enabled."""
        if self._interceptor_chain is None:
            return instance
        try:
            return Proxy(instance, self._interceptor_chain)
        except Exception:
            return instance

    def register(
        self,
        service: Type,
        implementation: Type,
        lifetime: Lifetime = Lifetime.SINGLETON,
    ) -> None:
        """注册服务"""
        self._services[service] = ServiceDescriptor(
            service=service, implementation=implementation, lifetime=lifetime
        )
        _log.debug(
            f"Registered service {service.__name__} -> {implementation.__name__}"
        )

    def register_instance(self, service: Type, instance: Any) -> None:
        """注册实例"""
        self._services[service] = ServiceDescriptor(
            service=service,
            implementation=type(instance),
            lifetime=Lifetime.SINGLETON,
            instance=instance,
        )
        # 缓存单例
        self._singletons[service] = instance
        _log.debug(f"Registered instance for {service.__name__}")

    def register_factory(self, service: Type, factory: Callable[..., Any]) -> None:
        """注册工厂函数"""
        self._services[service] = ServiceDescriptor(
            service=service,
            implementation=type(None),  # 工厂不使用实现类
            lifetime=Lifetime.TRANSIENT,
            factory=factory,
        )
        _log.debug(f"Registered factory for {service.__name__}")

    def resolve(self, service: Type) -> Any:
        """解析服务"""
        # 检查单例缓存
        if service in self._singletons:
            return self._singletons[service]

        # 创建实例
        instance = self._create_instance(service)

        # 如果是单例，缓存
        desc = self._services.get(service)
        if desc and desc.lifetime == Lifetime.SINGLETON:
            self._singletons[service] = instance

        return self._wrap(instance)

    def resolve_all(self, service: Type) -> List[Any]:
        """解析所有实现"""
        implementations = []
        for desc in self._services.values():
            if desc.service == service:
                impl = self._create_instance(desc.implementation)
                implementations.append(self._wrap(impl))
        return implementations

    def _create_instance(self, implementation: Type) -> Any:
        """创建实例"""
        desc = self._services.get(implementation)

        # 如果有工厂函数，使用工厂
        if desc and desc.factory:
            return desc.factory()

        # 如果有预注册实例
        if desc and desc.instance:
            return desc.instance

        # 尝试自动创建实例
        try:
            # 获取 __init__ 参数
            import inspect

            sig = inspect.signature(implementation.__init__)
            params = {}

            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue
                # 尝试解析依赖
                param_type = param.annotation
                if param_type != inspect.Parameter.empty:
                    try:
                        params[param_name] = self.resolve(param_type)
                    except:
                        # 如果无法解析，使用默认值
                        if param.default != inspect.Parameter.empty:
                            params[param_name] = param.default

            return implementation(**params)
        except Exception as e:
            _log.warning(f"Failed to create instance {implementation.__name__}: {e}")
            return implementation()

    def clear(self) -> None:
        """Clear container registrations and caches."""
        self._services.clear()
        self._singletons.clear()
        self._scopes.clear()

    def create_scope(self, scope_name: str) -> IScope:
        """创建作用域"""
        if scope_name in self._scopes:
            return self._scopes[scope_name]

        scope = ScopeImpl(self, scope_name)
        self._scopes[scope_name] = scope
        return scope

    @contextmanager
    def scope(self, scope_name: str):
        """作用域上下文管理器"""
        scope = self.create_scope(scope_name)
        try:
            yield scope
        finally:
            scope.close()

    def clear(self) -> None:
        """清空所有注册"""
        self._services.clear()
        self._singletons.clear()
        self._scopes.clear()
        _log.debug("Container cleared")
