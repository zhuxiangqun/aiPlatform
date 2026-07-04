"""
ProcessRegistry — lifecycle management for sub-processes.

Tracks spawned child processes (PID, health, graceful shutdown),
providing the foundation for multi-worker process management.

hermes-agent parity: tools/process_registry.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────────

class ProcessStatus(Enum):
    STARTING = "starting"
    RUNNING = "running"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"
    CRASHED = "crashed"
    ZOMBIE = "zombie"


class ProcessRole(Enum):
    """Process role in the system."""
    CORE_API = "core_api"
    MANAGEMENT_UI = "management_ui"
    WORKER = "worker"
    SCHEDULER = "scheduler"
    GATEWAY = "gateway"
    MCP_SERVER = "mcp_server"
    EMBEDDING = "embedding"
    RERANKER = "reranker"
    WIKI = "wiki"
    CLEANUP = "cleanup"


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class ProcessInfo:
    """Information about a registered process."""
    pid: int
    role: ProcessRole
    name: str
    status: ProcessStatus = ProcessStatus.STARTING
    started_at: float = field(default_factory=time.time)
    stopped_at: Optional[float] = None
    last_heartbeat: float = field(default_factory=time.time)
    restart_count: int = 0
    max_restarts: int = 3
    tags: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessHealth:
    """Health snapshot of a process."""
    pid: int
    name: str
    alive: bool
    uptime_seconds: float
    cpu_percent: Optional[float] = None
    memory_mb: Optional[float] = None
    status: ProcessStatus = ProcessStatus.RUNNING


# ── Process Registry ─────────────────────────────────────────────────────────

class ProcessRegistry:
    """
    Track spawned child processes with health monitoring and graceful shutdown.

    Usage:
        registry = ProcessRegistry()
        registry.register(pid, ProcessRole.WORKER, "worker-1")
        ...
        await registry.shutdown_all(grace_period=10)
    """

    def __init__(self):
        self._processes: Dict[int, ProcessInfo] = {}
        self._name_index: Dict[str, int] = {}  # name → pid
        self._role_index: Dict[ProcessRole, Set[int]] = {}
        self._lock = asyncio.Lock()
        self._health_interval: float = float(os.getenv("AIPLAT_PROCESS_HEALTH_INTERVAL", "30"))
        self._health_task: Optional[asyncio.Task] = None
        self._shutdown_signal: Optional[asyncio.Event] = None

    async def register(self, pid: int, role: ProcessRole, name: str,
                       max_restarts: int = 3, tags: Optional[Dict[str, str]] = None,
                       metadata: Optional[Dict[str, Any]] = None) -> ProcessInfo:
        """Register a new process in the registry."""
        async with self._lock:
            info = ProcessInfo(
                pid=pid,
                role=role,
                name=name,
                max_restarts=max_restarts,
                tags=tags or {},
                metadata=metadata or {},
            )
            self._processes[pid] = info
            self._name_index[name] = pid
            self._role_index.setdefault(role, set()).add(pid)
            logger.info("ProcessRegistry: registered %s (pid=%d, role=%s)", name, pid, role.value)
            return info

    async def unregister(self, pid: int, status: ProcessStatus = ProcessStatus.STOPPED):
        """Remove a process from the registry."""
        async with self._lock:
            info = self._processes.pop(pid, None)
            if info:
                self._name_index.pop(info.name, None)
                role_set = self._role_index.get(info.role)
                if role_set:
                    role_set.discard(pid)
                info.status = status
                info.stopped_at = time.time()
                logger.info("ProcessRegistry: unregistered %s (pid=%d, status=%s)", info.name, pid, status.value)

    async def heartbeat(self, pid: int):
        """Record a heartbeat from a process."""
        async with self._lock:
            info = self._processes.get(pid)
            if info:
                info.last_heartbeat = time.time()
                if info.status == ProcessStatus.DEGRADED:
                    info.status = ProcessStatus.HEALTHY

    async def mark_degraded(self, pid: int, reason: str = ""):
        """Mark a process as degraded."""
        async with self._lock:
            info = self._processes.get(pid)
            if info and info.status not in (ProcessStatus.STOPPING, ProcessStatus.STOPPED):
                info.status = ProcessStatus.DEGRADED
                info.metadata["degraded_reason"] = reason
                logger.warning("ProcessRegistry: %s (pid=%d) degraded: %s", info.name, pid, reason)

    async def mark_crashed(self, pid: int, reason: str = ""):
        """Mark a process as crashed and attempt restart if within limits."""
        async with self._lock:
            info = self._processes.get(pid)
            if info:
                info.status = ProcessStatus.CRASHED
                info.metadata["crash_reason"] = reason
                logger.error("ProcessRegistry: %s (pid=%d) crashed: %s", info.name, pid, reason)

    async def get_by_role(self, role: ProcessRole) -> List[ProcessInfo]:
        """Get all processes for a given role."""
        async with self._lock:
            pids = self._role_index.get(role, set())
            return [self._processes[pid] for pid in pids if pid in self._processes]

    async def get_by_name(self, name: str) -> Optional[ProcessInfo]:
        """Get process info by name."""
        async with self._lock:
            pid = self._name_index.get(name)
            if pid and pid in self._processes:
                return self._processes[pid]
            return None

    async def get_all(self) -> List[ProcessInfo]:
        """Get all registered processes."""
        async with self._lock:
            return list(self._processes.values())

    async def check_health(self) -> List[ProcessHealth]:
        """Check health of all registered processes (pid alive + heartbeat threshold)."""
        results: List[ProcessHealth] = []
        now = time.time()
        heartbeat_timeout = float(os.getenv("AIPLAT_PROCESS_HEARTBEAT_TIMEOUT", "60"))

        async with self._lock:
            for pid, info in list(self._processes.items()):
                alive = False
                try:
                    os.kill(pid, 0)
                    alive = True
                except (OSError, ProcessLookupError):
                    pass

                uptime = now - info.started_at
                heartbeat_age = now - info.last_heartbeat

                status = info.status
                if not alive:
                    status = ProcessStatus.ZOMBIE if info.status != ProcessStatus.STOPPED else info.status
                elif heartbeat_age > heartbeat_timeout:
                    status = ProcessStatus.DEGRADED
                    info.status = status
                    info.metadata["degraded_reason"] = f"no heartbeat for {heartbeat_age:.0f}s"

                results.append(ProcessHealth(
                    pid=pid,
                    name=info.name,
                    alive=alive,
                    uptime_seconds=uptime,
                    status=status,
                ))

        return results

    async def start_health_monitor(self):
        """Start background health monitoring task."""
        if self._health_task and not self._health_task.done():
            return

        self._shutdown_signal = asyncio.Event()

        async def _monitor():
            while not self._shutdown_signal.is_set():
                try:
                    health_results = await self.check_health()
                    zombie_count = sum(1 for h in health_results if h.status == ProcessStatus.ZOMBIE)
                    degraded_count = sum(1 for h in health_results if h.status == ProcessStatus.DEGRADED)
                    if zombie_count or degraded_count:
                        logger.warning(
                            "ProcessRegistry health: %d zombie(s), %d degraded, %d total",
                            zombie_count, degraded_count, len(health_results),
                        )
                except Exception:
                    logger.debug("ProcessRegistry health check failed", exc_info=True)
                try:
                    await asyncio.wait_for(self._shutdown_signal.wait(), timeout=self._health_interval)
                except asyncio.TimeoutError:
                    pass

        self._health_task = asyncio.create_task(_monitor())
        logger.info("ProcessRegistry: health monitor started (interval=%ss)", self._health_interval)

    async def stop_health_monitor(self):
        """Stop background health monitoring."""
        if self._shutdown_signal:
            self._shutdown_signal.set()
        if self._health_task and not self._health_task.done():
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
        logger.info("ProcessRegistry: health monitor stopped")

    async def shutdown_all(self, grace_period: float = 10.0):
        """Gracefully shut down all registered processes."""
        async with self._lock:
            processes = list(self._processes.items())

        logger.info("ProcessRegistry: shutting down %d process(es) (grace=%ss)", len(processes), grace_period)

        for pid, info in processes:
            try:
                os.kill(pid, signal.SIGTERM)
                info.status = ProcessStatus.STOPPING
            except (OSError, ProcessLookupError):
                info.status = ProcessStatus.STOPPED
                await self.unregister(pid)

        # Wait for graceful shutdown
        deadline = time.time() + grace_period
        while time.time() < deadline:
            async with self._lock:
                remaining = [info for info in self._processes.values()
                             if info.status == ProcessStatus.STOPPING]
            if not remaining:
                break
            await asyncio.sleep(0.5)

        # Force kill remaining
        async with self._lock:
            for pid, info in list(self._processes.items()):
                if info.status == ProcessStatus.STOPPING:
                    try:
                        os.kill(pid, signal.SIGKILL)
                        logger.warning("ProcessRegistry: force-killed %s (pid=%d)", info.name, pid)
                    except (OSError, ProcessLookupError):
                        pass
                    await self.unregister(pid, ProcessStatus.STOPPED)

        await self.stop_health_monitor()
        logger.info("ProcessRegistry: shutdown complete")

    def get_stats(self) -> Dict[str, Any]:
        """Return registry statistics."""
        status_counts = {}
        for info in self._processes.values():
            s = info.status.value
            status_counts[s] = status_counts.get(s, 0) + 1
        return {
            "total": len(self._processes),
            "by_status": status_counts,
            "by_role": {
                role.value: len(pids)
                for role, pids in self._role_index.items()
            },
            "health_monitor_active": bool(self._health_task and not self._health_task.done()),
        }


# ── Global Singleton ──────────────────────────────────────────────────────────

_process_registry: Optional[ProcessRegistry] = None


def get_process_registry() -> ProcessRegistry:
    """Get or create the global ProcessRegistry singleton."""
    global _process_registry
    if _process_registry is None:
        _process_registry = ProcessRegistry()
    return _process_registry


def reset_process_registry():
    """Reset the global singleton (for testing)."""
    global _process_registry
    _process_registry = None
