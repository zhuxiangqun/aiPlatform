"""Best-effort KB query → syscall_events telemetry (delivery kb-health / metrics).

Platform `POST /platform/kb/query` historically did not write ExecutionStore
events, so kb-health stayed at total_queries=0 despite successful HTTP queries.
This module records a soft `knowledge_retrieve` / `platform_kb_retrieve` row
aligned with `kb/metrics.py` filters — never raises into the query path.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def summarize_kb_query_result(out: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a compact result payload for metrics (count / items / citations)."""
    if not isinstance(out, dict):
        return {"count": 0, "items": []}
    kb = out.get("kb") if isinstance(out.get("kb"), dict) else {}
    items: List[Any] = []
    for key in ("items", "citations", "results", "hits"):
        raw = kb.get(key) if kb else None
        if raw is None and key in out:
            raw = out.get(key)
        if isinstance(raw, list) and raw:
            items = raw
            break
    count = len(items)
    if not count and isinstance(kb.get("count"), (int, float)):
        try:
            count = int(kb.get("count") or 0)
        except (TypeError, ValueError):
            count = 0
    # Cap stored items for audit size; metrics only need count/empty detection
    slim: List[Dict[str, Any]] = []
    for it in items[:8]:
        if not isinstance(it, dict):
            continue
        slim.append(
            {
                "source": str(it.get("source") or it.get("doc_id") or it.get("id") or "")[:200],
                "score": it.get("score"),
                "text": str(it.get("text") or it.get("snippet") or it.get("content") or "")[:200],
            }
        )
    result: Dict[str, Any] = {"count": count, "items": slim}
    if any(isinstance(it, dict) and (it.get("source") or it.get("doc_id")) for it in slim):
        result["citations"] = [
            {"source": it.get("source")} for it in slim if it.get("source")
        ]
    return result


async def record_kb_query_syscall(
    *,
    question: str,
    collection_id: str = "default",
    tenant_id: str = "",
    actor_id: str = "",
    request_id: str = "",
    out: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> bool:
    """Append knowledge_retrieve event. Returns True if persisted."""
    try:
        from core.api.core_facade import get_execution_store

        store = get_execution_store()
        if not store or not hasattr(store, "add_syscall_event"):
            return False
        now = time.time()
        result = summarize_kb_query_result(out)
        status = "error" if error else "ok"
        await store.add_syscall_event(
            {
                "kind": "knowledge_retrieve",
                "name": "platform_kb_retrieve",
                "status": status,
                "start_time": now,
                "end_time": now,
                "duration_ms": 0,
                "created_at": now,
                "tenant_id": tenant_id or None,
                "user_id": actor_id or None,
                "args": {
                    "question": str(question or "")[:500],
                    "collection_id": str(collection_id or "default"),
                    "request_id": str(request_id or "")[:80] or None,
                },
                "result": result,
                "error": error,
                "target_type": "kb_collection",
                "target_id": str(collection_id or "default"),
            }
        )
        return True
    except Exception as e:
        logger.debug("record_kb_query_syscall failed: %s", e, exc_info=True)
        return False
