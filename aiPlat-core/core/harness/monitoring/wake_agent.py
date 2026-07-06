"""WakeAgent — zero-token change detection for Agent waking.

A1-axis L4→L5 enabler. Monitors filesystem changes without consuming
any LLM inference budget. When changes are detected, triggers registered
callbacks to wake the Agent.

Config: AIPLAT_WAKE_PATHS (colon-separated paths to watch)
        AIPLAT_WAKE_INTERVAL (polling interval, default 60s)
"""
import asyncio, hashlib, os, sys, time
from typing import Callable, Optional

WAKE_PATHS = os.environ.get("AIPLAT_WAKE_PATHS", ".")
WAKE_INTERVAL = int(os.environ.get("AIPLAT_WAKE_INTERVAL", 60))


class WakeAgent:
    """Zero-token filesystem change detector.

    Polls configured paths at intervals, computes checksums, and
    fires callbacks when changes are detected. No LLM calls during
    the watching phase — purely deterministic hashing.
    """

    def __init__(self, paths: list[str] | None = None, interval: int = WAKE_INTERVAL):
        self.paths = [p for p in (paths or WAKE_PATHS.split(":")) if p.strip()]
        self.interval = interval
        self._checksums: dict[str, str] = {}
        self._callbacks: list[Callable] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._change_counter = 0

    def on_change(self, callback: Callable):
        """Register callback: callback(path, event_type) → None"""
        self._callbacks.append(callback)

    def _compute_checksum(self, path: str) -> str:
        """Compute a lightweight checksum of a directory tree or file."""
        if os.path.isfile(path):
            try:
                stat = os.stat(path)
                return hashlib.md5(f"{stat.st_mtime}:{stat.st_size}".encode()).hexdigest()
            except OSError:
                return ""
        elif os.path.isdir(path):
            hasher = hashlib.md5()
            for root, dirs, files in os.walk(path):
                dirs.sort()
                for fname in sorted(files):
                    fpath = os.path.join(root, fname)
                    try:
                        stat = os.stat(fpath)
                        hasher.update(f"{fpath}:{stat.st_mtime}:{stat.st_size}".encode())
                    except OSError:
                        pass
            return hasher.hexdigest()
        return ""

    async def _poll_loop(self):
        """Main polling loop — zero tokens, pure hashing."""
        while self._running:
            try:
                for path in self.paths:
                    if not os.path.exists(path):
                        continue
                    new_sum = self._compute_checksum(path)
                    old_sum = self._checksums.get(path, "")
                    if old_sum and new_sum and new_sum != old_sum:
                        event_type = "modified" if old_sum else "created"
                        for cb in self._callbacks:
                            try:
                                result = cb(path, event_type)
                                if asyncio.iscoroutine(result):
                                    await result
                            except Exception:
                                pass
                        self._change_counter += 1
                    self._checksums[path] = new_sum
            except Exception:
                pass
            await asyncio.sleep(self.interval)

    async def start(self):
        """Start the wake agent polling loop."""
        # Initial checksum baseline
        for path in self.paths:
            if os.path.exists(path):
                self._checksums[path] = self._compute_checksum(path)

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        print(f"  [WakeAgent] Watching {len(self.paths)} path(s) every {self.interval}s")

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    @property
    def changes_detected(self) -> int:
        return self._change_counter


# Singleton
_wake_agent: Optional[WakeAgent] = None


def get_wake_agent(paths: list[str] | None = None) -> WakeAgent:
    global _wake_agent
    if _wake_agent is None:
        _wake_agent = WakeAgent(paths=paths)
    return _wake_agent
