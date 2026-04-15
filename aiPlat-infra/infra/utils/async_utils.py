"""
Async Utils - 异步工具

文档位置：docs/utils/index.md
"""

import asyncio
import functools
import time
from typing import Any, Callable, Optional, TypeVar

T = TypeVar("T")


def async_retry(
    max_attempts: int = 3, backoff_factor: float = 2.0, exceptions: tuple = (Exception,)
):
    """
    异步重试装饰器

    Args:
        max_attempts: 最大尝试次数
        backoff_factor: 退避因子
        exceptions: 重试的异常类型

    Example:
        @async_retry(max_attempts=3, backoff_factor=2.0)
        async def call_api():
            return await api.request()
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            delay = 1.0
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(delay)
                        delay *= backoff_factor

            raise last_exception

        return wrapper

    return decorator


def async_timeout(seconds: float):
    """
    异步超时装饰器

    Args:
        seconds: 超时时间（秒）

    Example:
        @async_timeout(timeout=5.0)
        async def long_operation():
            await asyncio.sleep(10)
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                raise TimeoutError(f"{func.__name__} timed out after {seconds}s")

        return wrapper

    return decorator


async def run_in_executor(func: Callable, *args, **kwargs) -> Any:
    """
    在线程池中运行同步函数

    Args:
        func: 同步函数
        *args, **kwargs: 函数参数

    Returns:
        函数返回值
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


class SemaphorePool:
    """信号量池 - 控制并发数量"""

    def __init__(self, max_concurrent: int):
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def __aenter__(self):
        await self._semaphore.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._semaphore.release()

    async def __call__(self, func: Callable) -> Any:
        """作为装饰器使用"""

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            async with self:
                return await func(*args, **kwargs)

        return wrapper
