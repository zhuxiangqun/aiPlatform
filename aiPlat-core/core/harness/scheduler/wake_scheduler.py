"""WakeScheduler — zero-token autonomous wake trigger (A1.4 A1-axis L4→L5 enabler).

Monitors last user interaction and system degradation signals. When idle
beyond threshold (no human prompt), wakes up autonomously:

  1. Checks pending cron jobs (cron_loader)
  2. Generates a Goal from system state (GoalGenerator)
  3. Dispatches to GoalExecutor for autonomous repair/optimization

This is the "wakeAgent" pattern: the system takes initiative without user input.
Disabled by default (AIPLAT_WAKE_ENABLED=false) — safety-first, human opt-in.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

logger = logging.getLogger("aiplat.wake")


class WakeScheduler:
    """Background monitor that wakes the system when idle.

    Monitors a shared last-interaction timestamp (updated by sys_llm_generate /
    ReActLoop on each user message). When idle >= threshold, runs a scan-then-act
    cycle: check pending cron → generate improvement goals → execute reversible ones.
    """

    def __init__(
        self,
        *,
        enabled: bool = False,
        idle_minutes: int = 30,
        check_interval_seconds: int = 120,
    ):
        self._enabled = enabled
        self._idle_seconds = idle_minutes * 60
        self._check_interval = check_interval_seconds
        self._last_interaction: float = time.time()
        self._running = False
        self._wake_count = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    def mark_interaction(self) -> None:
        """Called by ReActLoop / sys_llm_generate on every user message."""
        self._last_interaction = time.time()

    async def start(self):
        if self._running:
            return
        self._running = True
        logger.info("[wake] scheduler started (idle=%ds, interval=%ds, enabled=%s)",
                     self._idle_seconds, self._check_interval, self._enabled)
        while self._running:
            try:
                await asyncio.sleep(self._check_interval)
                if not self._enabled:
                    continue
                idle = time.time() - self._last_interaction
                if idle < self._idle_seconds:
                    continue
                await self._on_wake(idle)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("[wake] cycle error: %s", e)

    async def _on_wake(self, idle_seconds: float):
        self._wake_count += 1
        logger.info("[wake] idle %.0fs → wake #%d", idle_seconds, self._wake_count)
        try:
            from core.harness.optimization.goal_generator import get_goal_generator
            goals = get_goal_generator().generate_auto_executable()
            if not goals:
                logger.debug("[wake] no auto-executable goals generated")
                return
            from core.harness.optimization.goal_executor import get_goal_executor
            executor = get_goal_executor()
            for goal in goals[:2]:  # max 2 per wake cycle
                success = await executor.execute_goal(goal)
                logger.info("[wake] executed goal=%s type=%s success=%s",
                            goal.goal_id[:12], goal.goal_type.value, success)
        except Exception as e:
            logger.debug("[wake] dispatch failed: %s", e)


# Singleton
_wake_scheduler: Optional[WakeScheduler] = None


def get_wake_scheduler() -> WakeScheduler:
    global _wake_scheduler
    if _wake_scheduler is None:
        enabled = os.getenv("AIPLAT_WAKE_ENABLED", "false").lower() in ("1", "true", "yes")
        idle_min = int(os.getenv("AIPLAT_WAKE_IDLE_MINUTES", "30") or "30")
        _wake_scheduler = WakeScheduler(enabled=enabled, idle_minutes=idle_min)
    return _wake_scheduler
