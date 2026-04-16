"""
DI Interceptors - 拦截器

文档位置：docs/di/index.md

常用拦截器：
- LoggingInterceptor: 日志拦截器
- TimingInterceptor: 计时拦截器
- CachingInterceptor: 缓存拦截器
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional, Dict, List


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
        self,
        method: Callable,
        instance: Any = None,
        args: tuple = (),
        kwargs: Optional[dict] = None,
        chain: Optional["InterceptorChain"] = None,
        index: int = 0,
    ):
        self._method = method
        self._instance = instance
        self._args = args
        self._kwargs = kwargs or {}
        self._chain = chain
        self._index = index

    def proceed(self) -> Any:
        """Proceed to next interceptor or execute original method."""
        if self._chain is not None and self._index < len(self._chain._interceptors):
            interceptor = self._chain._interceptors[self._index]
            next_inv = Invocation(
                method=self._method,
                instance=self._instance,
                args=self._args,
                kwargs=self._kwargs,
                chain=self._chain,
                index=self._index + 1,
            )
            return interceptor.intercept(next_inv)
        # If method is bound, call directly; otherwise pass instance as first arg.
        try:
            return self._method(*self._args, **self._kwargs)
        except TypeError:
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
        self._interceptors: List[Interceptor] = []

    def add(self, interceptor: Interceptor) -> None:
        self._interceptors.append(interceptor)

    def invoke(self, invocation: Invocation) -> Any:
        """执行拦截器链（标准 around 语义）"""
        if not self._interceptors:
            return invocation.proceed()
        invocation._chain = self
        invocation._index = 0
        return invocation.proceed()


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


class MetricsInterceptor(Interceptor):
    """简单指标拦截器：统计方法调用次数"""

    def __init__(self):
        self._counts: Dict[str, int] = {}

    def intercept(self, invocation: Invocation) -> Any:
        method_name = getattr(invocation.method, "__name__", "unknown")
        self._counts[method_name] = self._counts.get(method_name, 0) + 1
        return invocation.proceed()

    def get_count(self, method_name: str) -> int:
        return self._counts.get(method_name, 0)


class ErrorHandlingInterceptor(Interceptor):
    """错误处理拦截器：记录异常并抛出"""

    def __init__(self, logger=None):
        self._logger = logger

    def intercept(self, invocation: Invocation) -> Any:
        try:
            return invocation.proceed()
        except Exception as e:
            if self._logger:
                self._logger.exception(f"DI intercepted error: {e}")
            raise


class Proxy:
    """Dynamic proxy that applies interceptor chain to method calls."""

    def __init__(self, target: Any, chain: InterceptorChain):
        self.__dict__["_target"] = target
        self.__dict__["_chain"] = chain

    def __getattr__(self, item: str) -> Any:
        target = self.__dict__["_target"]
        attr = getattr(target, item)
        if not callable(attr):
            return attr

        def _wrapped(*args, **kwargs):
            inv = Invocation(method=attr, instance=target, args=args, kwargs=kwargs)
            return self.__dict__["_chain"].invoke(inv)

        _wrapped.__name__ = getattr(attr, "__name__", item)
        return _wrapped

    def __setattr__(self, key: str, value: Any) -> None:
        setattr(self.__dict__["_target"], key, value)
