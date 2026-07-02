"""
Health Check Registry — formal module health check framework.

Usage:
  Registry.register(MyHealthCheck())       # auto-discovered or manual
  report = await Registry.run_all()        # dependency-ordered execution
  status = Registry.get_status()           # cached status snapshot
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

log = logging.getLogger(__name__)


class Severity(str, Enum):
    CRITICAL = "critical"   # system cannot function without this
    HIGH = "high"           # service degraded
    MEDIUM = "medium"       # non-essential feature affected
    LOW = "low"             # cosmetic / informative


class Status(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    SKIPPED = "skipped"     # dependency unhealthy → skipped


@dataclass
class HealthResult:
    module: str
    status: Status
    severity: Severity
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class HealthReport:
    results: List[HealthResult] = field(default_factory=list)
    overall: Status = Status.UNKNOWN
    summary: Dict[str, int] = field(default_factory=lambda: {
        "healthy": 0, "degraded": 0, "unhealthy": 0, "skipped": 0, "unknown": 0,
    })
    total_duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)


class HealthCheck:
    """Base class for module health checks. Override `run()` and set class attrs."""

    module: str = ""                # unique module name
    severity: Severity = Severity.MEDIUM
    dependencies: List[str] = []     # module names that must be healthy first
    timeout_s: float = 15.0          # per-check timeout

    async def run(self) -> HealthResult:
        raise NotImplementedError

    def __repr__(self):
        return f"HealthCheck({self.module})"


class HealthCheckRegistry:
    """Singleton registry with dependency-aware parallel execution."""

    _instance: Optional["HealthCheckRegistry"] = None

    def __init__(self):
        self._checks: Dict[str, HealthCheck] = {}
        self._cache: Optional[HealthReport] = None
        self._cache_ts: float = 0.0
        self._cache_ttl: float = 300.0  # 5 minutes

    @classmethod
    def instance(cls) -> "HealthCheckRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, check: HealthCheck) -> None:
        if not check.module:
            raise ValueError(f"HealthCheck {check} must set 'module'")
        self._checks[check.module] = check
        self._cache = None  # invalidate cache

    def unregister(self, module: str) -> None:
        self._checks.pop(module, None)
        self._cache = None

    def get(self, module: str) -> Optional[HealthCheck]:
        return self._checks.get(module)

    def list_modules(self) -> List[str]:
        return sorted(self._checks.keys())

    def get_status(self, module: str) -> Optional[Status]:
        """Get cached status without running check."""
        if self._cache and time.time() - self._cache_ts < self._cache_ttl:
            for r in self._cache.results:
                if r.module == module:
                    return r.status
        return None

    def get_cached_report(self) -> Optional[HealthReport]:
        if self._cache and time.time() - self._cache_ts < self._cache_ttl:
            return self._cache
        return None

    async def run_all(self, modules: Optional[List[str]] = None) -> HealthReport:
        """Run checks in dependency order. If modules is specified, only those."""
        if modules:
            checks = {k: v for k, v in self._checks.items() if k in modules}
        else:
            checks = dict(self._checks)

        if not checks:
            return HealthReport(overall=Status.UNKNOWN)

        # Topological sort by dependencies
        ordered = self._topo_sort(checks)
        results: List[HealthResult] = []
        start = time.time()
        failed_modules: Set[str] = set()

        for batch in self._batch_by_dependencies(ordered, checks):
            tasks = []
            for m in batch:
                if any(d in failed_modules for d in checks[m].dependencies):
                    # Skip — dependency unhealthy
                    results.append(HealthResult(
                        module=m, status=Status.SKIPPED,
                        severity=checks[m].severity,
                        message=f"Skipped: dependency unhealthy ({', '.join(checks[m].dependencies)})",
                    ))
                    continue
                tasks.append(self._run_one(checks[m]))

            if tasks:
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                for br in batch_results:
                    if isinstance(br, Exception):
                        results.append(HealthResult(
                            module="unknown", status=Status.UNHEALTHY,
                            severity=Severity.CRITICAL,
                            message=f"Exception: {str(br)}",
                        ))
                    elif isinstance(br, HealthResult):
                        results.append(br)
                        if br.status in (Status.UNHEALTHY,):
                            failed_modules.add(br.module)

        # Compute overall
        summary = {"healthy": 0, "degraded": 0, "unhealthy": 0, "skipped": 0, "unknown": 0}
        for r in results:
            summary[r.status.value] = summary.get(r.status.value, 0) + 1

        if summary["unhealthy"] > 0:
            overall = Status.UNHEALTHY
        elif summary["degraded"] > 0:
            overall = Status.DEGRADED
        else:
            overall = Status.HEALTHY

        report = HealthReport(
            results=results,
            overall=overall,
            summary=summary,
            total_duration_ms=(time.time() - start) * 1000,
        )
        self._cache = report
        self._cache_ts = time.time()
        return report

    async def _run_one(self, check: HealthCheck) -> HealthResult:
        try:
            return await asyncio.wait_for(check.run(), timeout=check.timeout_s)
        except asyncio.TimeoutError:
            return HealthResult(
                module=check.module, status=Status.UNHEALTHY,
                severity=check.severity,
                message=f"Health check timed out after {check.timeout_s}s",
            )

    def _topo_sort(self, checks: Dict[str, HealthCheck]) -> List[str]:
        """Topological sort by dependency graph."""
        visited: Set[str] = set()
        result: List[str] = []

        def dfs(m: str, path: Set[str]):
            if m in visited:
                return
            if m in path:
                return  # ignore cycles
            path.add(m)
            for d in checks.get(m, HealthCheck()).dependencies:
                if d in checks:
                    dfs(d, path)
            path.discard(m)
            visited.add(m)
            result.append(m)

        for m in checks:
            dfs(m, set())
        return result

    def _batch_by_dependencies(self, ordered: List[str], checks: Dict[str, HealthCheck]) -> List[List[str]]:
        """Group modules that can run in parallel (no dependency on others in the same batch)."""
        batches: List[List[str]] = []
        remaining = set(ordered)
        while remaining:
            batch = []
            for m in sorted(remaining):
                if not any(d in remaining for d in checks[m].dependencies):
                    batch.append(m)
            if not batch:
                # Cycle or all have deps → run sequentially
                batch = [remaining.pop()]
            else:
                remaining -= set(batch)
            batches.append(batch)
        return batches


def get_registry() -> HealthCheckRegistry:
    return HealthCheckRegistry.instance()


__all__ = [
    "HealthCheck", "HealthCheckRegistry", "get_registry",
    "HealthResult", "HealthReport", "Severity", "Status",
]
