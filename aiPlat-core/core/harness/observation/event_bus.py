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
from typing import Any, Dict

_log = logging.getLogger("aiplat.event_bus")

# run_id → asyncio.Queue
_buses: Dict[str, asyncio.Queue] = {}
_running: bool = False
_dlq: asyncio.Queue | None = None
_worker_task: asyncio.Task | None = None
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
        如果没有订阅者，事件进入 DLQ 等待持久化。"""
        if not run_id or not _running:
            return
        q = _buses.get(run_id)
        if q is None:
            # No subscriber → buffer in DLQ for eventual persistence
            cls._enqueue_dlq(event)
            return
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            _log.warning("EventBus queue full for run_id=%s", run_id)
            cls._enqueue_dlq(event)  # fallback to DLQ

    @classmethod
    def _enqueue_dlq(cls, event: Dict[str, Any]) -> None:
        """Enqueue event to dead-letter queue for async persistence."""
        if _dlq is None:
            return
        try:
            _dlq.put_nowait(event)
        except asyncio.QueueFull:
            _log.warning("EventBus DLQ full, dropping event")

    @classmethod
    async def _dlq_worker(cls) -> None:
        """Background worker: flush DLQ events to SQLite in batches."""
        while _running:
            batch = []
            try:
                # Collect at least one event, then drain up to batch size
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
                    try:
                        # Use _insert_event_raw: pure SQL, no re-publish to EventBus
                        await store._insert_event_raw(evt)
                    except Exception:
                        pass
            except Exception:
                pass  # best-effort
            finally:
                for _ in batch:
                    _dlq.task_done()

    @classmethod
    def start(cls) -> None:
        """Start the EventBus service with DLQ worker."""
        global _running, _dlq, _worker_task
        _running = True
        _dlq = asyncio.Queue(maxsize=5000)
        try:
            loop = asyncio.get_running_loop()
            _worker_task = asyncio.create_task(cls._dlq_worker())
        except RuntimeError:
            pass
        _log.info("EventBus started with DLQ worker")

    @classmethod
    def stop(cls) -> None:
        """Stop the EventBus service."""
        global _running, _dlq, _worker_task
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
        _log.info("EventBus stopped")
