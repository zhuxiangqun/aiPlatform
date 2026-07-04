"""
File Watcher — generic file-system monitoring for config hot-reload.

Watches user-specified paths and invokes callbacks on changes.
Uses watchdog if available, falls back to polling.

Infra-agnostic: all paths are env-var-driven, no application-specific defaults.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class FileWatcher:
    u"""Watches files/directories and invokes callbacks on change events."""

    def __init__(self):
        self._watchers: Dict[str, List[Callable[[str], None]]] = {}  # path → callbacks
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._use_watchdog = False
        self._observer: Any = None
        self._poll_interval = 2.0

    def watch(self, path: str, callback: Callable[[str], None]) -> None:
        u"""Register a callback to be invoked when path changes."""
        if path not in self._watchers:
            self._watchers[path] = []
        self._watchers[path].append(callback)

    def start(self, *, poll_interval: float = 2.0) -> None:
        u"""Start watching. Tries watchdog first, falls back to polling."""
        self._poll_interval = poll_interval
        self._stop.clear()

        # Try watchdog
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class _Handler(FileSystemEventHandler):
                def __init__(self, watcher: FileWatcher):
                    self._watcher = watcher

                def on_modified(self, event):
                    if not event.is_directory:
                        self._watcher._notify(str(event.src_path))

            self._observer = Observer()
            handler = _Handler(self)
            watched_dirs = set()
            for p in self._watchers:
                d = str(Path(p).parent if not Path(p).is_dir() else p)
                if d not in watched_dirs:
                    self._observer.schedule(handler, d, recursive=True)
                    watched_dirs.add(d)
            self._observer.start()
            self._use_watchdog = True
            return
        except ImportError:
            pass

        # Fallback: polling
        self._use_watchdog = False
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="file_watcher")
        self._thread.start()

    def stop(self) -> None:
        u"""Stop watching."""
        self._stop.set()
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=3)
            self._observer = None
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def _notify(self, filepath: str) -> None:
        for path, callbacks in self._watchers.items():
            if Path(filepath).resolve() == Path(path).resolve():
                for cb in callbacks:
                    try:
                        cb(filepath)
                    except Exception as e:
                        logging.debug(str(e), exc_info=True)

    def _poll_loop(self) -> None:
        mtimes: Dict[str, float] = {}
        # Initial scan
        for p in self._watchers:
            try:
                mtimes[p] = Path(p).stat().st_mtime
            except OSError:
                mtimes[p] = 0

        while not self._stop.is_set():
            time.sleep(self._poll_interval)
            for p in self._watchers:
                if self._stop.is_set():
                    break
                try:
                    new_mtime = Path(p).stat().st_mtime
                    if p not in mtimes or new_mtime != mtimes[p]:
                        mtimes[p] = new_mtime
                        for cb in self._watchers[p]:
                            try:
                                cb(p)
                            except Exception as e:
                                logging.debug(str(e), exc_info=True)
                except OSError:
                    pass


# ── Global singleton ─────────────────────────────────────────────

_watcher: Optional[FileWatcher] = None


def get_file_watcher() -> FileWatcher:
    global _watcher
    if _watcher is None:
        _watcher = FileWatcher()
    return _watcher


def start_config_watcher(config_paths: List[str] = None) -> FileWatcher:
    u"""Start watching config files for hot-reload.

    config_paths: list of file paths to watch. Default from env var.
    """
    if config_paths is None:
        paths_env = os.getenv("AIPLAT_CONFIG_WATCH_PATHS", "")
        config_paths = [p.strip() for p in paths_env.split(",") if p.strip()]

    if not config_paths:
        return get_file_watcher()

    watcher = get_file_watcher()
    for p in config_paths:
        watcher.watch(p, _on_config_change)

    watcher.start()
    return watcher


def _on_config_change(filepath: str) -> None:
    u"""Hot-reload callback — dispatched on any watched file change."""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"config file changed: {filepath}")
    # Callbacks registered by upper layers (core/platform) handle the actual reload
    # Infra layer is agnostic — it only dispatches the event
