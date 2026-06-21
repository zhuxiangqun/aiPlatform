"""
LatencyTracker — In-memory request latency and congestion signal tracking.

Tracks per-model P95 latency via EWMA and congestion signals via
rolling request rate + HTTP 429 (rate limit) detection.

Used by ModelManager.select_by_purpose_list() to add latency_penalty
and congestion_penalty to model scoring.

Callers:
  - infra/management/model/manager.py (select_by_purpose_list scoring)
  - core/harness/utils/model_injection.py (generate_with_fallback success/failure)
"""

from __future__ import annotations

import time as _time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional


class LatencyTracker:
    """Per-model latency statistics with EWMA and congestion detection."""

    def __init__(self, window_seconds: int = 60, p95_threshold_ms: int = 10000,
                 rate_threshold: int = 10):
        self._window = window_seconds
        self._p95_threshold = p95_threshold_ms / 1000.0  # convert to seconds
        self._rate_threshold = rate_threshold

        # latency history: model_name → [(timestamp, elapsed_seconds), ...]
        self._latency: Dict[str, Deque[tuple]] = defaultdict(lambda: deque(maxlen=200))

        # request timestamps for rate calculation: model_name → [timestamp, ...]
        self._request_times: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=200))

        # HTTP 429 rate-limit cooldown: model_name → lockout_until_timestamp
        self._rate_limited_until: Dict[str, float] = {}

    def record_latency(self, model_name: str, elapsed_ms: float):
        """Record successful request latency in milliseconds."""
        now = _time.time()
        self._latency[model_name].append((now, elapsed_ms / 1000.0))
        self._request_times[model_name].append(now)

    def record_rate_limit(self, model_name: str, cooldown_seconds: float = 30.0):
        """Record HTTP 429 rate limit. Model gets penalty for cooldown_seconds."""
        self._rate_limited_until[model_name] = _time.time() + cooldown_seconds

    def p95_latency_seconds(self, model_name: str) -> float:
        """Calculate approximate P95 latency from recent history."""
        hist = self._latency[model_name]
        if not hist:
            return 0.0
        now = _time.time()
        # Only consider samples from the last window
        recent = sorted(v for t, v in hist if now - t < self._window)
        if not recent:
            return 0.0
        idx = int(len(recent) * 0.95)
        return recent[min(idx, len(recent) - 1)]

    def congestion_penalty(self, model_name: str) -> float:
        """Calculate congestion penalty (0 = no penalty, higher = more congested).

        Checks: request rate > threshold → penalty
                HTTP 429 active → heavy penalty
        """
        now = _time.time()
        penalty = 0.0

        # Check rate limiting (highest priority)
        if self._rate_limited_until.get(model_name, 0) > now:
            return 50.0  # Max penalty for rate-limited models

        # Check request rate
        recent_requests = sum(1 for t in self._request_times[model_name]
                              if now - t < self._window)
        rate = recent_requests / self._window
        if rate > self._rate_threshold * 2:
            penalty = 30.0
        elif rate > self._rate_threshold:
            penalty = 15.0

        return penalty


# Global singleton
_latency_tracker = LatencyTracker()


def get_latency_tracker() -> LatencyTracker:
    return _latency_tracker
