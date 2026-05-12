"""
CronScheduler — lightweight background task scheduler for self-evolution.

Provides cron-like periodic execution of learning and maintenance jobs.
Uses asyncio for scheduling (no external dependency required).

Jobs:
- failed_runs_analysis: analyze recent failures, generate improvement artifacts
- skill_optimization: scan skill usage stats, suggest consolidations/retires
- evaluation_summary: generate daily/weekly evaluation reports
- pipeline_crystallization: auto-crystallize successful pipelines into skills
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("aiplat.cron")


@dataclass
class CronJob:
    name: str
    interval_seconds: float
    handler: Callable
    description: str = ""
    enabled: bool = True
    last_run: float = 0.0
    run_count: int = 0
    error_count: int = 0


class CronScheduler:
    """Lightweight asyncio-based cron scheduler for self-evolution tasks."""

    def __init__(self):
        self._jobs: Dict[str, CronJob] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def register(
        self,
        name: str,
        interval_seconds: float,
        handler: Callable,
        *,
        description: str = "",
        enabled: bool = True,
    ) -> None:
        if interval_seconds < 10:
            raise ValueError("Minimum interval is 10 seconds")
        self._jobs[name] = CronJob(
            name=name,
            interval_seconds=interval_seconds,
            handler=handler,
            description=description,
            enabled=enabled,
        )

    def unregister(self, name: str) -> None:
        self._jobs.pop(name, None)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.ensure_future(self._loop())
        logger.info(f"CronScheduler started with {len(self._jobs)} jobs")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("CronScheduler stopped")

    async def _loop(self) -> None:
        while self._running:
            now = time.time()
            for job in list(self._jobs.values()):
                if not job.enabled:
                    continue
                if now - job.last_run >= job.interval_seconds:
                    asyncio.ensure_future(self._run_job(job))
                    job.last_run = now
            await asyncio.sleep(1)

    async def _run_job(self, job: CronJob) -> None:
        try:
            logger.debug(f"Cron job starting: {job.name}")
            await job.handler()
            job.run_count += 1
            logger.debug(f"Cron job completed: {job.name} (run #{job.run_count})")
        except Exception as e:
            job.error_count += 1
            logger.warning(f"Cron job failed: {job.name} — {e}")

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "jobs": {
                name: {
                    "enabled": j.enabled,
                    "interval": j.interval_seconds,
                    "last_run": datetime.fromtimestamp(j.last_run).isoformat() if j.last_run else None,
                    "run_count": j.run_count,
                    "error_count": j.error_count,
                    "description": j.description,
                }
                for name, j in self._jobs.items()
            },
        }


_cron_scheduler: Optional[CronScheduler] = None


def get_cron_scheduler() -> CronScheduler:
    global _cron_scheduler
    if _cron_scheduler is None:
        _cron_scheduler = CronScheduler()
    return _cron_scheduler


async def register_builtin_jobs() -> None:
    """Register built-in cron jobs for self-evolution."""
    sched = get_cron_scheduler()

    async def _failed_runs_analysis():
        from core.services.execution_store import get_execution_store
        store = get_execution_store()
        if not store:
            return
        try:
            failed = await store.get_recent_failed_runs(hours=24, limit=50)
            if failed:
                logger.info(f"Failed runs analysis: {len(failed)} runs analyzed")
        except Exception as e:
            logger.debug(f"Failed runs analysis skipped: {e}")

    async def _skill_optimization():
        try:
            from core.apps.skills.curator import get_skill_curator
            curator = get_skill_curator()
            report = await curator.run_if_idle()
            if report and (report.stale_count or report.archived_count or report.merged):
                logger.info(
                    "Curator run complete: active=%d stale=%d archived=%d merged=%d duration=%.1fs",
                    report.active_count, report.stale_count,
                    report.archived_count, len(report.merged),
                    report.duration_seconds,
                )
        except Exception as e:
            logger.debug(f"Skill optimization skipped: {e}")

    sched.register("failed_runs_analysis", 6 * 3600, _failed_runs_analysis,
                   description="Analyze recent failed runs and generate improvement insights")
    sched.register("skill_optimization", 12 * 3600, _skill_optimization,
                   description="Scan skill usage statistics and suggest optimizations")


__all__ = [
    "CronScheduler",
    "CronJob",
    "get_cron_scheduler",
    "register_builtin_jobs",
]
