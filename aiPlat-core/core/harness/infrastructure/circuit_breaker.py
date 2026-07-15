"""
BaseCircuitBreaker — shared state machine for system fault tolerance.

Four implementations previously existed independently (LLM, Wiki, MCP, Tool),
each with their own open/closed/half_open logic. This base class consolidates
the shared pattern.

States: CLOSED (normal) → OPEN (fuse blown) → HALF_OPEN (probing) → CLOSED or OPEN.

Usage:
  class MyBreaker(BaseCircuitBreaker):
      pass
  
  breaker = MyBreaker(failure_threshold=5, recovery_timeout=30.0)
  if breaker.allow():
      try:
          do_work()
          breaker.success()
      except Exception:
          breaker.failure()
          raise
"""

from __future__ import annotations

import logging
import time
from typing import Optional


logger = logging.getLogger("aiplat.circuit_breaker")


class BaseCircuitBreaker:
    """Generic circuit breaker with standard open/closed/half-open semantics.

    Inherit and override hooks if you need custom logging or recovery behavior.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        *,
        name: str = "circuit_breaker",
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.name = name
        self._failures = 0
        self._last_failure_ts = 0.0
        self._open_ts = 0.0
        self._state = "closed"  # closed | open | half_open

    # ── Public API ──

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (requests blocked)."""
        if self._state == "open":
            if time.time() - self._open_ts > self.recovery_timeout:
                self._state = "half_open"
                return False
            return True
        return False

    def allow(self) -> bool:
        """Return True if the request should be attempted.
        
        Returns True when state is 'closed' or 'half_open'.
        Returns False when state is 'open' (not yet recovered).
        Half-open state is automatically transitioned from 'open' when
        recovery_timeout has elapsed.
        """
        if self._state == "open":
            if time.time() - self._open_ts > self.recovery_timeout:
                self._state = "half_open"
                logger.debug("[%s] Circuit → HALF_OPEN (probing)", self.name)
                return True
            return False
        return True  # closed or half_open

    def success(self):
        """Record a successful request. Resets failure count."""
        self._failures = 0
        if self._state != "closed":
            self._state = "closed"
            logger.info("[%s] Circuit → CLOSED (recovered)", self.name)

    def failure(self):
        """Record a failed request. May open the circuit."""
        self._failures += 1
        self._last_failure_ts = time.time()
        if self._failures >= self.failure_threshold and self._state != "open":
            self._state = "open"
            self._open_ts = time.time()
            logger.warning(
                "[%s] Circuit → OPEN after %d consecutive failures",
                self.name, self._failures,
            )
            self._on_open()

    # ── Backward-compatible aliases ──

    def allow_request(self) -> bool:
        return self.allow()

    def record_success(self):
        self.success()

    def record_failure(self):
        self.failure()

    # ── Hooks for subclasses ──

    def _on_open(self):
        """Hook called when circuit transitions to OPEN. Override for custom logging."""
        pass

    def _on_close(self):
        """Hook called when circuit transitions to CLOSED."""
        pass

    def reset(self):
        """Force reset to closed state."""
        self._failures = 0
        self._state = "closed"
        self._open_ts = 0.0
        self._last_failure_ts = 0.0
        logger.info("[%s] Circuit → CLOSED (manual reset)", self.name)
