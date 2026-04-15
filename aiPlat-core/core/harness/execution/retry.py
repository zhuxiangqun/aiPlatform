"""
Retry Manager Module

Provides retry logic for failed operations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Type
import asyncio
import time


@dataclass
class RetryConfig:
    """Retry configuration"""
    max_attempts: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True


class RetryStrategy(ABC):
    """
    Retry strategy interface
    """
    
    @abstractmethod
    def get_delay(self, attempt: int) -> float:
        """Get delay for attempt"""
        pass


class ExponentialBackoff(RetryStrategy):
    """Exponential backoff strategy"""
    
    def __init__(self, config: RetryConfig):
        self._config = config
    
    def get_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay"""
        delay = min(
            self._config.initial_delay * (self._config.exponential_base ** attempt),
            self._config.max_delay
        )
        
        if self._config.jitter:
            import random
            delay = delay * (0.5 + random.random())
        
        return delay


class LinearBackoff(RetryStrategy):
    """Linear backoff strategy"""
    
    def __init__(self, config: RetryConfig):
        self._config = config
    
    def get_delay(self, attempt: int) -> float:
        """Calculate linear backoff delay"""
        delay = min(
            self._config.initial_delay * attempt,
            self._config.max_delay
        )
        
        if self._config.jitter:
            import random
            delay = delay * (0.5 + random.random())
        
        return delay


class RetryManager:
    """
    Retry manager for handling transient failures
    """

    def __init__(
        self,
        config: Optional[RetryConfig] = None,
        strategy: Optional[RetryStrategy] = None
    ):
        self._config = config or RetryConfig()
        self._strategy = strategy or ExponentialBackoff(self._config)
        self._retryable_exceptions: tuple = (Exception,)

    def set_retryable_exceptions(self, exceptions: tuple) -> None:
        """Set exceptions that should trigger retry"""
        self._retryable_exceptions = exceptions

    async def execute(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function with retry logic
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Any: Function result
            
        Raises:
            Exception: Last exception if all retries fail
        """
        last_exception = None
        
        for attempt in range(self._config.max_attempts):
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
                    
            except self._retryable_exceptions as e:
                last_exception = e
                
                if attempt < self._config.max_attempts - 1:
                    delay = self._strategy.get_delay(attempt)
                    await asyncio.sleep(delay)
                else:
                    raise last_exception
        
        raise last_exception

    async def execute_with_result(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> tuple[bool, Any]:
        """
        Execute function and return success status
        
        Returns:
            tuple: (success, result_or_error)
        """
        try:
            result = await self.execute(func, *args, **kwargs)
            return True, result
        except Exception as e:
            return False, e


def create_retry_manager(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    exponential: bool = True
) -> RetryManager:
    """
    Create retry manager
    
    Args:
        max_attempts: Maximum retry attempts
        initial_delay: Initial delay between retries
        exponential: Use exponential backoff
        
    Returns:
        RetryManager: Configured retry manager
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        initial_delay=initial_delay,
    )
    
    strategy = ExponentialBackoff(config) if exponential else LinearBackoff(config)
    
    return RetryManager(config=config, strategy=strategy)