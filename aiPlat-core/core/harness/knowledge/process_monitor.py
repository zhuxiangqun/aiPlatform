"""Process Monitor — 流程监控 Dashboard 后端（v2.6 / N09 K11）。

职责：聚合 `state_history.state_changes`（按 tenant+domain 召回前过滤）。
非目标：不写状态机；不负责 process_instances 租户列（见 orchestrator）。
"""
from __future__ import annotations

from core.harness.knowledge.domain_router import DomainRouter
import os as _os
import sqlite3 as _sqlite3
import time as _time
from datetime import datetime, timedelta
from typing import Any, Dict, List


def _db_path() -> str:
    """与 state_history 共用库路径，避免监控读空库。

    Returns:
        state_changes.db 绝对路径。
    """
    # 为什么：N09 K11 — 旧实现用 get_aiplat_data_dir 旁路库，与写入路径分裂
    from core.harness.ontology_engine.state_history import _db_path as _hist_db

    return _hist_db()


def _get_conn():
    path = _db_path()
    conn = _sqlite3.connect(path, timeout=5.0)
    conn.row_factory = _sqlite3.Row
    return conn


def _tid(tenant_id: str | None) -> str:
    return (tenant_id or "").strip() or DomainRouter.default_tenant()


def state_distribution(
    domain_id: str, *, tenant_id: str = DomainRouter.default_tenant()
) -> List[Dict[str, Any]]:
    """Count instances per class per state. Returns [{class_name, state_name, count}].

    Args:
        domain_id: domain 标识。
        tenant_id: 租户；召回前过滤（N09 K11）。
    """
    path = _db_path()
    if not _os.path.exists(path):
        return []
    tid = _tid(tenant_id)
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT class_name, to_state, COUNT(*) as cnt FROM state_changes
               WHERE domain_id = ? AND tenant_id = ? AND to_state != ''
               GROUP BY class_name, to_state ORDER BY class_name, cnt DESC""",
            (domain_id, tid),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "class_name": r["class_name"],
            "state_name": r["to_state"],
            "count": r["cnt"],
        }
        for r in rows
    ]


def bottleneck_analysis(
    domain_id: str, limit: int = 10, *, tenant_id: str = DomainRouter.default_tenant()
) -> List[Dict[str, Any]]:
    """Find entities stuck in their current state the longest.

    Args:
        domain_id: domain 标识。
        limit: 返回条数上限。
        tenant_id: 租户；召回前过滤（N09 K11）。
    """
    path = _db_path()
    if not _os.path.exists(path):
        return []
    tid = _tid(tenant_id)
    conn = _get_conn()
    now = _time.time()
    try:
        rows = conn.execute(
            """SELECT entity_name, class_name, to_state, MAX(timestamp) as last_ts
               FROM state_changes
               WHERE domain_id = ? AND tenant_id = ? AND to_state != ''
               GROUP BY entity_name ORDER BY last_ts ASC LIMIT ?""",
            (domain_id, tid, limit),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "entity_name": r["entity_name"],
            "class_name": r["class_name"],
            "current_state": r["to_state"],
            "stuck_seconds": round(now - r["last_ts"]),
        }
        for r in rows
    ]


def sla_violations(
    domain_id: str, *, tenant_id: str = DomainRouter.default_tenant()
) -> List[Dict[str, Any]]:
    """Find instances with time_elapsed transitions that have triggered.

    Args:
        domain_id: domain 标识。
        tenant_id: 租户；召回前过滤（N09 K11）。
    """
    path = _db_path()
    if not _os.path.exists(path):
        return []
    tid = _tid(tenant_id)
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT entity_name, class_name, from_state, to_state, timestamp,
                      trigger_type, transition_desc
               FROM state_changes
               WHERE domain_id = ? AND tenant_id = ?
                 AND trigger_type = 'time_elapsed'
               ORDER BY timestamp DESC LIMIT 50""",
            (domain_id, tid),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "entity_name": r["entity_name"],
            "class_name": r["class_name"],
            "from_state": r["from_state"],
            "to_state": r["to_state"],
            "triggered_at": r["timestamp"],
            "description": r["transition_desc"] or "",
        }
        for r in rows
    ]


def trend_data(
    domain_id: str, days: int = 7, *, tenant_id: str = DomainRouter.default_tenant()
) -> List[Dict[str, Any]]:
    """Daily state transition counts for the last N days.

    Args:
        domain_id: domain 标识。
        days: days 参数。
        tenant_id: 租户；召回前过滤（N09 K11）。
    """
    path = _db_path()
    if not _os.path.exists(path):
        return []
    tid = _tid(tenant_id)
    conn = _get_conn()
    today = datetime.now().date()
    results = []
    try:
        for offset in range(days):
            day = today - timedelta(days=offset)
            day_str = day.isoformat()
            day_start = datetime(day.year, day.month, day.day).timestamp()
            day_end = day_start + 86400
            rows = conn.execute(
                """SELECT class_name, to_state, COUNT(*) as cnt FROM state_changes
                   WHERE domain_id = ? AND tenant_id = ?
                     AND timestamp >= ? AND timestamp < ?
                   GROUP BY class_name, to_state""",
                (domain_id, tid, day_start, day_end),
            ).fetchall()
            transitions = [
                {
                    "class_name": r["class_name"],
                    "state_name": r["to_state"],
                    "count": r["cnt"],
                }
                for r in rows
            ]
            results.append(
                {
                    "date": day_str,
                    "transitions": transitions,
                    "total": sum(t["count"] for t in transitions),
                }
            )
    finally:
        conn.close()
    return results


def state_transition_stats(
    domain_id: str, *, tenant_id: str = DomainRouter.default_tenant()
) -> Dict[str, Any]:
    """Get summary stats: total transitions, most common transitions.

    Args:
        domain_id: domain 标识。
        tenant_id: 租户；召回前过滤（N09 K11）。
    """
    path = _db_path()
    if not _os.path.exists(path):
        return {"total_transitions": 0, "top_transitions": []}
    tid = _tid(tenant_id)
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM state_changes WHERE domain_id = ? AND tenant_id = ?",
            (domain_id, tid),
        ).fetchone()
        total = row[0] if row else 0
        top = conn.execute(
            """SELECT class_name, from_state, to_state, COUNT(*) as cnt
               FROM state_changes
               WHERE domain_id = ? AND tenant_id = ?
                 AND from_state != '' AND to_state != ''
               GROUP BY class_name, from_state, to_state
               ORDER BY cnt DESC LIMIT 10""",
            (domain_id, tid),
        ).fetchall()
    finally:
        conn.close()
    return {
        "total_transitions": total,
        "top_transitions": [
            {
                "class_name": r["class_name"],
                "from": r["from_state"],
                "to": r["to_state"],
                "count": r["cnt"],
            }
            for r in top
        ],
    }
