"""
Health Collector — periodic background health check aggregator.

Usage:
  collector = HealthCollector(interval_s=300)
  collector.start()
  # ... queries get cached results
  collector.stop()
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from .registry import HealthCheckRegistry, HealthReport, Status, get_registry

log = logging.getLogger(__name__)


class HealthCollector:
    """Periodic background health data collector with event-driven push."""

    def __init__(self, *, interval_s: float = 300.0, registry: Optional[HealthCheckRegistry] = None):
        self._registry = registry or get_registry()
        self._interval = interval_s
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._last_report: Optional[HealthReport] = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        log.info("HealthCollector started (interval=%.0fs)", self._interval)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        log.info("HealthCollector stopped")

    async def collect_once(self) -> HealthReport:
        report = await self._registry.run_all()
        self._last_report = report
        self._on_report(report)
        return report

    def get_last_report(self) -> Optional[HealthReport]:
        return self._last_report

    async def _loop(self) -> None:
        # Run once immediately
        try:
            await self.collect_once()
        except Exception:
            log.exception("Initial health collection failed")
        while self._running:
            await asyncio.sleep(self._interval)
            if not self._running:
                break
            try:
                await self.collect_once()
            except Exception:
                log.exception("Periodic health collection failed")

    def _on_report(self, report: HealthReport) -> None:
        """Called after each collection. Override for custom event handling."""
        changes = []
        for r in report.results:
            if r.status in (Status.UNHEALTHY, Status.DEGRADED):
                changes.append(f"{r.module}={r.status.value}")

        if report.overall != Status.HEALTHY:
            log.warning(
                "Health: overall=%s healthy=%d degraded=%d unhealthy=%d changed=[%s]",
                report.overall.value,
                report.summary["healthy"],
                report.summary["degraded"],
                report.summary["unhealthy"],
                ", ".join(changes[:5]),
            )


__all__ = ["HealthCollector"]
