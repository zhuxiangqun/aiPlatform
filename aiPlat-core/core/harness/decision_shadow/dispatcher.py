"""Bounded shadow dispatcher.

When disabled (default): try_enqueue is a no-op that records drop=disabled.
No worker thread is started while disabled. DomainRouter does not call this yet.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, Optional

from core.harness.decision_shadow.audit import redact_payload
from core.harness.decision_shadow.client import DecisionClient
from core.harness.decision_shadow.config import (
    DecisionShadowConfig,
    load_decision_shadow_config,
)

logger = logging.getLogger(__name__)

_DISPATCHER: Optional["ShadowDispatcher"] = None
_DISPATCHER_LOCK = threading.Lock()


class ShadowDispatcher:
    """Process-local dispatcher with drop counters (Phase 1 skeleton)."""

    def __init__(self, config: Optional[DecisionShadowConfig] = None):
        """初始化。

        Args:
            config: config 参数。
        """
        self._config = config or load_decision_shadow_config()
        self._client = DecisionClient(self._config)
        self._queue: Deque[Dict[str, Any]] = deque()
        self._lock = threading.Lock()
        self._drops: Dict[str, int] = {
            "disabled": 0,
            "queue_full": 0,
            "not_sampled": 0,
            "error": 0,
        }
        self._enqueue_attempts = 0
        self._enqueued = 0
        self._started_at = time.time()

    @property
    def config(self) -> DecisionShadowConfig:
        """config。
        """
        return self._config

    def try_enqueue(self, payload: Dict[str, Any]) -> bool:
        """Non-blocking enqueue. Returns True only if accepted into the queue.

        Args:
            payload: 载荷 dict。
        """
        with self._lock:
            self._enqueue_attempts += 1
            cfg = self._config
            if not cfg.enabled:
                self._drops["disabled"] = int(self._drops.get("disabled", 0)) + 1
                return False
            try:
                rate = float(cfg.sample_rate)
                if rate <= 0.0:
                    self._drops["not_sampled"] = int(self._drops.get("not_sampled", 0)) + 1
                    return False
                if rate < 1.0:
                    token = str(
                        payload.get("query_hash") or payload.get("trace_id") or ""
                    )
                    bucket = (hash(token) % 10_000) / 10_000.0 if token else 0.0
                    if bucket >= rate:
                        self._drops["not_sampled"] = (
                            int(self._drops.get("not_sampled", 0)) + 1
                        )
                        return False

                record = redact_payload(payload, store_raw_text=cfg.store_raw_text)
                record.setdefault("trigger", cfg.trigger)
                record.setdefault("model", cfg.model)

                if len(self._queue) >= max(1, int(cfg.queue_size)):
                    self._drops["queue_full"] = int(self._drops.get("queue_full", 0)) + 1
                    return False
                self._queue.append(record)
                self._enqueued += 1
                return True
            except Exception:
                logger.warning("decision_shadow try_enqueue failed", exc_info=True)
                self._drops["error"] = int(self._drops.get("error", 0)) + 1
                return False

    def queue_depth(self) -> int:
        """queue_depth。
        """
        with self._lock:
            return len(self._queue)

    def status(self) -> Dict[str, Any]:
        """status。
        """
        cfg = self._config
        with self._lock:
            drops = dict(self._drops)
            depth = len(self._queue)
            enqueued = self._enqueued
            attempts = self._enqueue_attempts
        return {
            "ok": True,
            "enabled": bool(cfg.enabled),
            "sample_rate": cfg.sample_rate,
            "trigger": cfg.trigger,
            "queue_size": cfg.queue_size,
            "queue_depth": depth,
            "timeout_ms": cfg.timeout_ms,
            "endpoint_configured": bool(cfg.endpoint),
            "store_raw_text": bool(cfg.store_raw_text),
            "enqueue_attempts": attempts,
            "enqueued": enqueued,
            "drops": drops,
            "classify_hook_wired": False,
            "uptime_s": round(time.time() - self._started_at, 1),
            "scope": "process",
            "honesty": (
                "muted skeleton; DomainRouter.classify NOT hooked; "
                "default enabled=false; ≠ Ollaya live; ≠ token savings; "
                "≠ Go Phase 1 traffic / ≠ 1b replace"
            ),
            "config": cfg.to_public_dict(),
        }


def get_shadow_dispatcher() -> ShadowDispatcher:
    """获取 shadow_dispatcher。
    """
    global _DISPATCHER
    with _DISPATCHER_LOCK:
        if _DISPATCHER is None:
            _DISPATCHER = ShadowDispatcher()
        return _DISPATCHER


def reset_shadow_dispatcher_for_tests(
    config: Optional[DecisionShadowConfig] = None,
) -> ShadowDispatcher:
    """Replace process singleton (unit tests only).

    Args:
        config: config 参数。
    """
    global _DISPATCHER
    with _DISPATCHER_LOCK:
        _DISPATCHER = ShadowDispatcher(config=config)
        return _DISPATCHER
