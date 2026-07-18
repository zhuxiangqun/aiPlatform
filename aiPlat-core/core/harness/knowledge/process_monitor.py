u"""
Process Monitor — 流程监控 Dashboard 后端 (v2.6).

Reuses state_history.db for aggregation—no separate table needed.
Provides: state distribution, bottleneck analysis, SLA violations, trends.
"""
from __future__ import annotations

import os as _os
import sqlite3 as _sqlite3
import time as _time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

DB_PATH = _os.path.expanduser("~/.aiplat/state_changes.db")


def _get_conn():
    conn = _sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = _sqlite3.Row
    return conn


def state_distribution(domain_id: str) -> List[Dict[str, Any]]:
    u"""Count instances per class per state. Returns [{class_name, state_name, count}]."""
    if not _os.path.exists(DB_PATH):
        return []
    conn = _get_conn()
    rows = conn.execute(
        """SELECT class_name, to_state, COUNT(*) as cnt FROM state_changes
           WHERE domain_id = ? AND to_state != ''
           GROUP BY class_name, to_state ORDER BY class_name, cnt DESC""",
        (domain_id,),
    ).fetchall()
    conn.close()
    return [{"class_name": r["class_name"], "state_name": r["to_state"], "count": r["cnt"]} for r in rows]


def bottleneck_analysis(domain_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    u"""Find entities stuck in their current state the longest."""
    if not _os.path.exists(DB_PATH):
        return []
    conn = _get_conn()
    now = _time.time()
    rows = conn.execute(
        """SELECT entity_name, class_name, to_state, MAX(timestamp) as last_ts FROM state_changes
           WHERE domain_id = ? AND to_state != ''
           GROUP BY entity_name ORDER BY last_ts ASC LIMIT ?""",
        (domain_id, limit),
    ).fetchall()
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


def sla_violations(domain_id: str) -> List[Dict[str, Any]]:
    u"""Find instances with time_elapsed transitions that have triggered (from state_history)."""
    if not _os.path.exists(DB_PATH):
        return []
    conn = _get_conn()
    rows = conn.execute(
        """SELECT entity_name, class_name, from_state, to_state, timestamp, trigger_type, transition_desc
           FROM state_changes WHERE domain_id = ? AND trigger_type = 'time_elapsed'
           ORDER BY timestamp DESC LIMIT 50""",
        (domain_id,),
    ).fetchall()
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


def trend_data(domain_id: str, days: int = 7) -> List[Dict[str, Any]]:
    u"""Daily state transition counts for the last N days."""
    if not _os.path.exists(DB_PATH):
        return []
    conn = _get_conn()
    today = datetime.now().date()
    results = []
    for offset in range(days):
        day = today - timedelta(days=offset)
        day_str = day.isoformat()
        day_start = datetime(day.year, day.month, day.day).timestamp()
        day_end = day_start + 86400
        rows = conn.execute(
            """SELECT class_name, to_state, COUNT(*) as cnt FROM state_changes
               WHERE domain_id = ? AND timestamp >= ? AND timestamp < ?
               GROUP BY class_name, to_state""",
            (domain_id, day_start, day_end),
        ).fetchall()
        transitions = [{"class_name": r["class_name"], "state_name": r["to_state"], "count": r["cnt"]} for r in rows]
        results.append({"date": day_str, "transitions": transitions, "total": sum(t["count"] for t in transitions)})
    conn.close()
    return results


def state_transition_stats(domain_id: str) -> Dict[str, Any]:
    u"""Get summary stats: total transitions, most common transitions."""
    if not _os.path.exists(DB_PATH):
        return {"total_transitions": 0, "top_transitions": []}
    conn = _get_conn()
    row = conn.execute("SELECT COUNT(*) FROM state_changes WHERE domain_id = ?", (domain_id,)).fetchone()
    total = row[0] if row else 0
    top = conn.execute(
        """SELECT class_name, from_state, to_state, COUNT(*) as cnt FROM state_changes
           WHERE domain_id = ? AND from_state != '' AND to_state != ''
           GROUP BY class_name, from_state, to_state ORDER BY cnt DESC LIMIT 10""",
        (domain_id,),
    ).fetchall()
    conn.close()
    return {
        "total_transitions": total,
        "top_transitions": [
            {"class_name": r["class_name"], "from": r["from_state"], "to": r["to_state"], "count": r["cnt"]}
            for r in top
        ],
    }
