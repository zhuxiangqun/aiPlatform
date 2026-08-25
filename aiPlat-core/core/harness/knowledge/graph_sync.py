"""
GraphSyncHandler — keeps capability + code graphs in sync with resource mutations.

Subscribes to RESOURCE_MUTATED events via the Observability EventBus.
On receiving an event, clears both graph caches after a 2-second debounce,
so the next consumer call (overview, capability page, diagnostics) rebuilds naturally.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

_log = logging.getLogger(__name__)


class GraphSyncHandler:
    """Centralized handler for resource mutation → graph cache invalidation."""

    def __init__(self):
        self._debounce_task: Optional[asyncio.Task] = None
        self._debounce_secs = 2.0

    async def on_resource_mutated(self, event):
        """Debounced cache clear: coalesces rapid mutations into one invalidation."""
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        self._debounce_task = asyncio.create_task(self._clear_after_debounce())

    async def _clear_after_debounce(self):
        await asyncio.sleep(self._debounce_secs)
        try:
            from core.harness.knowledge.capability_graph import clear_capability_cache
            clear_capability_cache()
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        try:
            from core.harness.knowledge.code_graph import clear_cache
            clear_cache()
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        # 2026-08-25: ABox 缓存同步失效——wiki 变更时 GraphIndex（本体实例图）也需重建，
        # 避免 kb_graph（文档级三元组）与 GraphIndex（本体实例图）双图库查询不一致
        # （知识管理审计 Q3 收尾；语义边界不变：各自真相源，本步保证 ABox 缓存不陈旧）。
        try:
            from core.harness.knowledge.knowledge_abox_builder import invalidate_abox_cache
            invalidate_abox_cache()
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    @classmethod
    async def wire(cls):
        """Register handler on the Observability EventBus. Safe to call multiple times."""
        try:
            from core.harness.observability.events import EventBus, EventType
            bus = EventBus.get_instance()
            handler = cls()
            bus.subscribe(EventType.RESOURCE_MUTATED, handler.on_resource_mutated)
            _log.info("GraphSyncHandler wired to EventBus")
        except Exception:
            _log.debug("EventBus unavailable; skipping GraphSyncHandler wire", exc_info=True)
