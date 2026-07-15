"""
LifecycleManager — organized startup/shutdown for DI-registered services.

Registered callbacks are invoked in registration order on start/stop.
Graceful shutdown: stop callbacks are always called, even if some fail.
"""

from __future__ import annotations
import asyncio
import logging
from typing import Any, Callable, List, Optional, Tuple

logger = logging.getLogger("aiplat.di.lifecycle")


class LifecycleManager:
    """Manages startup/shutdown sequences for DI-registered services.
    
    Usage:
        lm = LifecycleManager()
        lm.register_startup("enterprise_gateway", gateway.start)
        lm.register_shutdown("enterprise_gateway", gateway.stop)
        await lm.start()
        # ... application runs ...
        await lm.stop()
    """

    def __init__(self, *, container: Any = None):
        self._container = container
        self._startup: List[Tuple[str, Callable]] = []
        self._shutdown: List[Tuple[str, Callable]] = []
        self._started = False

    def register_startup(self, name: str, callback: Callable):
        """Register a startup callback. Callbacks run in registration order."""
        self._startup.append((name, callback))

    def register_shutdown(self, name: str, callback: Callable):
        """Register a shutdown callback. Callbacks run in reverse registration order."""
        self._shutdown.append((name, callback))

    async def start(self) -> None:
        """Run all startup callbacks in order. Errors are logged but don't block."""
        for name, callback in self._startup:
            try:
                result = callback()
                if asyncio.iscoroutine(result):
                    await result
                logger.debug("Lifecycle: started '%s'", name)
            except Exception as e:
                logger.warning("Lifecycle: '%s' startup failed: %s", name, e)
        self._started = True
        logger.info("Lifecycle: %d services started", len(self._startup))

    async def stop(self) -> None:
        """Run all shutdown callbacks in reverse order. Always runs all callbacks."""
        for name, callback in reversed(self._shutdown):
            try:
                result = callback()
                if asyncio.iscoroutine(result):
                    await result
                logger.debug("Lifecycle: stopped '%s'", name)
            except Exception as e:
                logger.warning("Lifecycle: '%s' shutdown failed: %s", name, e)
        self._started = False
        logger.info("Lifecycle: %d services stopped", len(self._shutdown))

    def is_started(self) -> bool:
        return self._started

    @property
    def container(self) -> Any:
        return self._container
