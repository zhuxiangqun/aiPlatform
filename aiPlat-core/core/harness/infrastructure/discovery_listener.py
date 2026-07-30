"""
DiscoveryListener — 监听自动发现的数据源目录变更 (Phase 41).

监听 ~/.aiplat/datasources/auto_discovered/ 目录，
新文件出现时 → 自动加载 DataSourceConfig → AutoRegisterEngine 验证+注册。

安全: 发现的源默认 source=auto, PolicyGate DENY until approved.
"""

from __future__ import annotations

import asyncio
import logging
import os as _os
import time as _time
from typing import Any, Dict, Optional

logger = logging.getLogger("aiplat.discovery_listener")


class DiscoveryListener:
    """目录变更监听器。

    轮询 ~/.aiplat/datasources/auto_discovered/ 发现新 YAML 文件。
    """

    _WATCH_DIR = _os.path.expanduser("~/.aiplat/datasources/auto_discovered")
    _CHECK_INTERVAL = 30  # seconds

    def __init__(self, *, enabled: bool = False):
        self._enabled = enabled
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._seen_files: Dict[str, float] = {}
        self._discovery_count = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        logger.info("[discovery_listener] started (dir=%s, interval=%ds)",
                     self._WATCH_DIR, self._CHECK_INTERVAL)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def _watch_loop(self) -> None:
        _os.makedirs(self._WATCH_DIR, exist_ok=True)
        while self._running:
            try:
                await asyncio.sleep(self._CHECK_INTERVAL)
                if not self._enabled:
                    continue
                await self._scan_directory()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("[discovery_listener] scan error: %s", e)

    async def _scan_directory(self) -> None:
        if not _os.path.isdir(self._WATCH_DIR):
            return
        try:
            entries = _os.listdir(self._WATCH_DIR)
        except Exception:
            return

        for entry in entries:
            if not (entry.endswith(".yaml") or entry.endswith(".json")):
                continue
            fp = _os.path.join(self._WATCH_DIR, entry)
            try:
                mtime = _os.path.getmtime(fp)
            except Exception:
                continue

            if entry in self._seen_files and self._seen_files[entry] >= mtime:
                continue
            self._seen_files[entry] = mtime

            config = self._load_config(fp, entry)
            if config:
                await self._on_new_config(config, fp)

    def _load_config(self, fp: str, entry: str) -> Optional[Dict[str, Any]]:
        try:
            if entry.endswith(".yaml"):
                import yaml as _yaml
                with open(fp, "r") as f:
                    return _yaml.safe_load(f)
            else:
                import json as _json
                with open(fp, "r") as f:
                    return _json.load(f)
        except Exception as e:
            logger.debug("[discovery_listener] failed to load %s: %s", entry, e)
            return None

    async def _on_new_config(self, config: Dict[str, Any], filepath: str) -> None:
        """New config found → validate and attempt auto-registration."""
        try:
            from core.harness.infrastructure.auto_register import get_auto_register_engine
            engine = get_auto_register_engine()
            result = await engine.try_register(config)
            logger.info(
                "[discovery_listener] %s → %s (connected=%s)",
                config.get("name", "unknown"),
                result.status,
                result.connection_ok,
            )
            self._discovery_count += 1
        except Exception as e:
            logger.debug("[discovery_listener] auto_register failed: %s", e)

    def stats(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "running": self._running,
            "watch_dir": self._WATCH_DIR,
            "discovery_count": self._discovery_count,
            "seen_files": len(self._seen_files),
        }


_discovery_listener: Optional[DiscoveryListener] = None


def get_discovery_listener() -> DiscoveryListener:
    global _discovery_listener
    if _discovery_listener is None:
        enabled = _os.getenv("AIPLAT_DISCOVERY_ENABLED", "false").lower() in (
            "1", "true", "yes",
        )
        _discovery_listener = DiscoveryListener(enabled=enabled)
    return _discovery_listener
