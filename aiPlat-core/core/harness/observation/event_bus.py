"""
EventBus — 通用观测层
为所有系统调用事件提供实时发布/订阅机制。

使用方法：
  from core.harness.observation.event_bus import EventBus
  EventBus.publish(run_id, event)     # 发布事件
  q = EventBus.subscribe(run_id)      # 订阅事件流
  EventBus.unsubscribe(run_id)        # 取消订阅
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

_log = logging.getLogger("aiplat.event_bus")

# run_id → asyncio.Queue
_buses: Dict[str, asyncio.Queue] = {}
_running: bool = False
_dlq: asyncio.Queue | None = None
_worker_task: asyncio.Task | None = None
_loop: Optional[asyncio.AbstractEventLoop] = None
_BATCH_SIZE = 50


class EventBus:
    @classmethod
    def subscribe(cls, run_id: str) -> asyncio.Queue:
        """Subscribe to events for a run_id. Returns an asyncio.Queue that receives events."""
        q = _buses.get(run_id)
        if q is None:
            q = asyncio.Queue(maxsize=1000)
            _buses[run_id] = q
        return q

    @classmethod
    def unsubscribe(cls, run_id: str) -> None:
        """Unsubscribe from events for a run_id."""
        _buses.pop(run_id, None)

    @classmethod
    def publish(cls, run_id: str, event: Dict[str, Any]) -> None:
        """发布事件到指定 run 的订阅者。非阻塞。
        支持跨线程：Agent 在独立线程跑时，经 call_soon_threadsafe 投递到主 loop。

        No-subscriber path must NOT DLQ: syscall_events already persisted by
        ``add_syscall_event``, and RunGraph SSE envelopes (``type=graph_*``)
        lack kind/name — DLQ insert created ghost ``event/unknown`` rows
        (run-5fc64fbf7c96 steps 27–32).
        """
        if not run_id:
            return
        q = _buses.get(run_id)
        if q is None:
            return

        def _put() -> None:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                _log.warning("EventBus queue full for run_id=%s", run_id)
                if _running:
                    cls._enqueue_dlq(event)

        loop = _loop
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if loop is not None and loop.is_running() and running is not loop:
            try:
                loop.call_soon_threadsafe(_put)
            except Exception:
                _log.debug("EventBus threadsafe publish failed", exc_info=True)
        else:
            _put()

    @classmethod
    def _is_syscall_shaped(cls, event: Dict[str, Any]) -> bool:
        """DLQ may only persist audit rows — not SSE graph envelopes."""
        if not isinstance(event, dict):
            return False
        # RunGraph SSE: {type: graph_upsert|graph_done, node: {...}}
        et = str(event.get("type") or "")
        if et.startswith("graph_"):
            return False
        kind = str(event.get("kind") or "").strip()
        name = str(event.get("name") or "").strip()
        return bool(kind and name)

    @classmethod
    def _enqueue_dlq(cls, event: Dict[str, Any]) -> None:
        """Enqueue overflow events for async persistence (subscriber queue full only)."""
        if _dlq is None:
            return
        if not cls._is_syscall_shaped(event):
            _log.debug("EventBus DLQ skip non-syscall event keys=%s", list(event.keys())[:8])
            return

        def _put() -> None:
            try:
                _dlq.put_nowait(event)
            except asyncio.QueueFull:
                _log.warning("EventBus DLQ full, dropping event")

        if _loop is not None and _loop.is_running():
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is not _loop:
                try:
                    _loop.call_soon_threadsafe(_put)
                    return
                except Exception:
                    _log.debug("EventBus DLQ threadsafe enqueue failed", exc_info=True)
        _put()

    @classmethod
    async def _dlq_worker(cls) -> None:
        """Background worker: flush DLQ events to SQLite in batches."""
        while _running:
            batch = []
            try:
                batch.append(await asyncio.wait_for(_dlq.get(), timeout=5))
                for _ in range(_BATCH_SIZE - 1):
                    try:
                        batch.append(_dlq.get_nowait())
                    except asyncio.QueueEmpty:
                        break
            except asyncio.TimeoutError:
                continue

            if not batch:
                continue

            try:
                from core.services.execution_store import get_execution_store
                store = get_execution_store()
                for evt in batch:
                    if not cls._is_syscall_shaped(evt):
                        continue
                    try:
                        await store._insert_event_raw(evt)
                    except Exception as e:
                        logging.debug(str(e), exc_info=True)
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            finally:
                for _ in batch:
                    _dlq.task_done()

    @classmethod
    def start(cls) -> None:
        """Start the EventBus service with DLQ worker."""
        global _running, _dlq, _worker_task, _loop
        _running = True
        _dlq = asyncio.Queue(maxsize=5000)
        try:
            _loop = asyncio.get_running_loop()
            _worker_task = asyncio.create_task(cls._dlq_worker())
        except RuntimeError:
            _loop = None
        _log.info("EventBus started with DLQ worker")

    @classmethod
    def stop(cls) -> None:
        """Stop the EventBus service."""
        global _running, _dlq, _worker_task, _loop
        _running = False
        if _worker_task:
            _worker_task.cancel()
        _buses.clear()
        if _dlq:
            while not _dlq.empty():
                try:
                    _dlq.get_nowait()
                    _dlq.task_done()
                except asyncio.QueueEmpty:
                    break
        _loop = None
        _log.info("EventBus stopped")
