"""
DI Interceptors - 拦截器

文档位置：docs/di/index.md

常用拦截器：
- LoggingInterceptor: 日志拦截器
- TimingInterceptor: 计时拦截器
- CachingInterceptor: 缓存拦截器
"""

from abc import ABC, abstractmethod
from typing import Any, Callable


class Interceptor(ABC):
    """拦截器基类"""

    @abstractmethod
    def intercept(self, invocation: "Invocation") -> Any:
        """
        执行拦截

        Args:
            invocation: 调用上下文

        Returns:
            执行结果
        """
        pass


class Invocation:
    """
    调用上下文

    封装方法调用信息
    """

    def __init__(
        self, method: Callable, instance: Any, args: tuple = (), kwargs: dict = None
    ):
        self._method = method
        self._instance = instance
        self._args = args
        self._kwargs = kwargs or {}

    def proceed(self) -> Any:
        """执行原方法"""
        return self._method(self._instance, *self._args, **self._kwargs)

    @property
    def method(self) -> Callable:
        return self._method

    @property
    def instance(self) -> Any:
        return self._instance


class InterceptorChain:
    """拦截器链"""

    def __init__(self):
        self._interceptors = []

    def add(self, interceptor: Interceptor) -> None:
        self._interceptors.append(interceptor)

    def invoke(self, invocation: Invocation) -> Any:
        """执行拦截器链"""
        if not self._interceptors:
            return invocation.proceed()

        # 简单的链式调用
        result = invocation.proceed()
        for interceptor in self._interceptors:
            result = interceptor.intercept(
                Invocation(
                    lambda: result,  # 模拟方法
                    invocation.instance,
                )
            )
        return result


class LoggingInterceptor(Interceptor):
    """日志拦截器"""

    def __init__(self, logger=None):
        self._logger = logger

    def intercept(self, invocation: Invocation) -> Any:
        method_name = getattr(invocation.method, "__name__", "unknown")
        if self._logger:
            self._logger.debug(f"Calling {method_name}")
        result = invocation.proceed()
        if self._logger:
            self._logger.debug(f"Completed {method_name}")
        return result


class TimingInterceptor(Interceptor):
    """计时拦截器"""

    def __init__(self):
        self._timings: dict = {}

    def intercept(self, invocation: Invocation) -> Any:
        import time

        method_name = getattr(invocation.method, "__name__", "unknown")
        start = time.time()
        result = invocation.proceed()
        elapsed = time.time() - start
        self._timings[method_name] = elapsed
        return result

    def get_timing(self, method_name: str) -> float:
        return self._timings.get(method_name, 0.0)


class CachingInterceptor(Interceptor):
    """缓存拦截器"""

    def __init__(self, cache: dict = None):
        self._cache = cache or {}

    def intercept(self, invocation: Invocation) -> Any:
        method_name = getattr(invocation.method, "__name__", "unknown")
        key = f"{method_name}:{invocation._args}"
        if key in self._cache:
            return self._cache[key]
        result = invocation.proceed()
        self._cache[key] = result
        return result
