"""
Background task queue for wiki maintenance operations.

Replaces fragile subprocess-in-string patterns with a proper asyncio queue.
Tasks are enqueued synchronously (safe from sync write_page/delete_page) and
processed asynchronously by a worker started in server.py's lifespan.
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any, Dict

_log = logging.getLogger("aiplat.wiki_bg")


_queue: asyncio.Queue = None
_worker_task: asyncio.Task = None


def _get_queue() -> asyncio.Queue:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue(maxsize=100)
    return _queue


def enqueue(task_type: str, **kwargs) -> None:
    """Enqueue a background task. Safe to call from sync or async context."""
    q = _get_queue()
    try:
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(lambda: q.put_nowait({"type": task_type, **kwargs}))
    except RuntimeError:
        q.put_nowait({"type": task_type, **kwargs})


async def _process_one(task: Dict[str, Any]) -> None:
    task_type = task.get("type", "")
    try:
        if task_type == "rebuild_metrics":
            from core.harness.knowledge.knowledge_validator import compute_ontology_metrics
            cid = task.get("collection_id", "default")
            compute_ontology_metrics(collection_id=cid, force_fresh=True)
        elif task_type == "auto_atomize":
            from core.harness.knowledge.wiki_engine import _auto_atomize_by_title_impl
            title = task.get("title", "")
            cid = task.get("collection_id", "default")
            await _auto_atomize_by_title_impl(title, cid)
        elif task_type == "propagate_marking":
            from core.harness.knowledge.wiki_engine import _propagate_marking
            title = task.get("title", "")
            marking = task.get("marking", "public")
            cid = task.get("collection_id", "default")
            _propagate_marking(title, marking, cid)
        else:
            _log.warning(f"Unknown background task type: {task_type}")
    except Exception:
        _log.error(f"Background task {task_type} failed:\n{traceback.format_exc()}")


async def start_worker() -> None:
    """Start the background task worker (called from server.py lifespan)."""
    global _worker_task
    if _worker_task is None:
        q = _get_queue()
        _worker_task = asyncio.create_task(_run_worker(q))
        _log.info("Wiki background task worker started")


async def stop_worker() -> None:
    """Stop the background task worker (called from server.py lifespan shutdown)."""
    global _worker_task
    if _worker_task is not None:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None
        _log.info("Wiki background task worker stopped")


async def _run_worker(q: asyncio.Queue) -> None:
    while True:
        try:
            task = await q.get()
            await _process_one(task)
        except asyncio.CancelledError:
            break
        except Exception:
            _log.error(f"Worker loop error:\n{traceback.format_exc()}")
