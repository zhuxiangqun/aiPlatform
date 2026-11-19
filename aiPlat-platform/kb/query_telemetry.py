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
from core.api.core_facade import DomainRouter

logger = logging.getLogger(__name__)


def summarize_kb_query_result(out: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a compact result payload for metrics (count / items / citations).

    Args:
        out: out 参数。
    """
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
    collection_id: str = DomainRouter.default_collection(),
    tenant_id: str = "",
    actor_id: str = "",
    request_id: str = "",
    out: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    store: Any = None,
    duration_ms: Optional[float] = None,
) -> bool:
    """Append knowledge_retrieve event. Returns True if persisted.

    Args:
        question: question 参数。
        collection_id: collection 标识。
        tenant_id: 租户 ID。
        actor_id: actor 标识。
        request_id: request 标识。
        out: out 参数。
        error: error 参数。
        store: store 参数。
        duration_ms: 真实查询耗时（毫秒）；缺省记 0 并仍写事件。
    """
    try:
        if store is None:
            from core.api.core_facade import get_execution_store

            store = get_execution_store()
        if not store or not hasattr(store, "add_syscall_event"):
            return False
        now = time.time()
        result = summarize_kb_query_result(out)
        status = "error" if error else "ok"
        try:
            dur = float(duration_ms) if duration_ms is not None else 0.0
        except (TypeError, ValueError):
            dur = 0.0
        if dur < 0:
            dur = 0.0
        start = now - (dur / 1000.0) if dur else now
        await store.add_syscall_event(
            {
                "kind": "knowledge_retrieve",
                "name": "platform_kb_retrieve",
                "status": status,
                "start_time": start,
                "end_time": now,
                "duration_ms": dur,
                "created_at": now,
                "tenant_id": tenant_id or None,
                "user_id": actor_id or None,
                "args": {
                    "question": str(question or "")[:500],
                    "collection_id": str(collection_id or DomainRouter.default_collection()),
                    "request_id": str(request_id or "")[:80] or None,
                },
                "result": result,
                "error": error,
                "target_type": "kb_collection",
                "target_id": str(collection_id or DomainRouter.default_collection()),
            }
        )
        # 为什么：F1 deepen — 查询路径同时写入 SLO 样本；软失败
        tid = str(tenant_id or "").strip()
        if tid:
            try:
                from core.api.core_facade import record_knowledge_slo_sample

                if dur > 0:
                    record_knowledge_slo_sample(
                        "query_p95_ms",
                        dur,
                        tenant_id=tid,
                        source="platform_kb_retrieve",
                        ok=(status == "ok"),
                    )
                cites = result.get("citations") if isinstance(result, dict) else None
                hit = 1.0 if (isinstance(cites, list) and cites) else 0.0
                record_knowledge_slo_sample(
                    "citation_coverage",
                    hit,
                    tenant_id=tid,
                    source="platform_kb_retrieve",
                    ok=(status == "ok"),
                )
            except Exception:
                logger.debug("slo sample from kb query soft-fail", exc_info=True)
        return True
    except Exception as e:
        logger.debug("record_kb_query_syscall failed: %s", e, exc_info=True)
        return False
