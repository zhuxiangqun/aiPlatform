"""
Logging Manager — infrastructure logging management.

Provides health checks, status, and diagnostics for the logging subsystem.
Wired into the management dashboard in Phase 7.
"""

from __future__ import annotations
import logging
from typing import Any, Dict

logger = logging.getLogger("infra.logging")

class LoggingManager:
    """Manages logging configuration and health for the infra layer."""
    def __init__(self):
        self._initialized = True
        self._default_level = logging.getLevelName(logging.root.level)

    def health(self) -> Dict[str, Any]:
        return {"status": "healthy", "default_level": self._default_level}

    def status(self) -> Dict[str, Any]:
        return {"initialized": self._initialized, "handlers": len(logging.root.handlers)}

    def diagnostics(self) -> Dict[str, Any]:
        return {"root_logger": logging.root.name, "effective_level": self._default_level}
