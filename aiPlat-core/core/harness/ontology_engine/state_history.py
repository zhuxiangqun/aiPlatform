"""
State History Persistence — SQLite-based storage for state machine transitions.

Schema:
  state_changes(id, domain_id, entity_name, class_name,
                from_state, to_state, trigger_type, transition_desc,
                doc_id, chunk_id, timestamp, tags)

Connection: module-level persistent WAL connection + threading.Lock.
Eliminates per-call connect/disconnect overhead on the hot write path.
"""

from __future__ import annotations
import logging
import threading

import json as _json
import os as _os
import time as _time
from pathlib import Path as _Path
from typing import Any, Dict, List, Optional


def _db_path() -> str:
    home = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat"))
    db_dir = home / "state_history"
    db_dir.mkdir(parents=True, exist_ok=True)
    return str(db_dir / "state_changes.db")


# ── Module-level persistent connection ──
from core.harness.infrastructure.db_utils import create_persistent_conn

_conn = create_persistent_conn(_db_path())
_lock = threading.Lock()


def _ensure_schema(conn):
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS state_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain_id TEXT NOT NULL,
            entity_name TEXT NOT NULL,
            class_name TEXT NOT NULL,
            from_state TEXT NOT NULL,
            to_state TEXT NOT NULL,
            trigger_type TEXT NOT NULL,
            transition_desc TEXT DEFAULT '',
            doc_id TEXT DEFAULT '',
            chunk_id TEXT DEFAULT '',
            timestamp REAL NOT NULL,
            tags TEXT DEFAULT '[]'
        )
    """)
    _conn.execute("CREATE INDEX IF NOT EXISTS idx_domain_entity ON state_changes(domain_id, entity_name)")
    _conn.execute("CREATE INDEX IF NOT EXISTS idx_domain_ts ON state_changes(domain_id, timestamp)")
    # Feedback table for L5 satisfaction scoring
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL DEFAULT '',
            query_text TEXT NOT NULL DEFAULT '',
            rating INTEGER CHECK (rating BETWEEN 1 AND 5),
            is_helpful INTEGER DEFAULT NULL,
            domain_id TEXT NOT NULL DEFAULT '',
            timestamp REAL NOT NULL
        )
    """)
    _conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_domain ON feedback(domain_id, timestamp)")
    _conn.commit()


# Run once at module load
_ensure_schema(_conn)


def close_connection():
    """Close the persistent connection (called on server shutdown)."""
    global _conn
    if _conn:
        _conn.close()
        _conn = None


def record_transition(
    domain_id: str,
    entity_name: str,
    class_name: str,
    from_state: str,
    to_state: str,
    trigger_type: str,
    *,
    transition_desc: str = "",
    doc_id: str = "",
    chunk_id: str = "",
    tags: Optional[List[str]] = None,
) -> None:
    """Record a single state transition."""
    with _lock:
        _conn.execute(
            """INSERT INTO state_changes
               (domain_id, entity_name, class_name, from_state, to_state,
                trigger_type, transition_desc, doc_id, chunk_id, timestamp, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                domain_id, entity_name, class_name, from_state, to_state,
                trigger_type, transition_desc, doc_id, chunk_id,
                _time.time(), _json.dumps(tags or [], ensure_ascii=False),
            ),
        )
        _conn.commit()


def get_entity_history(domain_id: str, entity_name: str) -> List[Dict[str, Any]]:
    """Get all state changes for a specific entity in a domain."""
    with _lock:
        rows = _conn.execute(
            """SELECT id, entity_name, class_name, from_state, to_state,
                      trigger_type, transition_desc, doc_id, chunk_id, timestamp, tags
               FROM state_changes
               WHERE domain_id = ? AND entity_name = ?
               ORDER BY timestamp""",
            (domain_id, entity_name),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def get_domain_history(domain_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Get recent state changes for a domain."""
    with _lock:
        rows = _conn.execute(
            """SELECT id, entity_name, class_name, from_state, to_state,
                      trigger_type, transition_desc, doc_id, chunk_id, timestamp, tags
               FROM state_changes
               WHERE domain_id = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (domain_id, limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def _row_to_dict(row) -> dict:
    tags = []
    try:
        tags = _json.loads(row[10] or "[]")
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return {
        "id": row[0],
        "entity_name": row[1],
        "class_name": row[2],
        "from_state": row[3],
        "to_state": row[4],
        "trigger_type": row[5],
        "transition_desc": row[6] or "",
        "doc_id": row[7] or "",
        "chunk_id": row[8] or "",
        "timestamp": row[9],
        "tags": tags,
    }


# ══════════════════════════════════════════════════════════════
# Time Series Window Statistics (文章三层特征工程 Layer 1)
# ══════════════════════════════════════════════════════════════

def get_entity_window_stats(
    domain_id: str,
    entity_name: str = "",
    *,
    window_hours: float = 24.0,
    class_name: str = "",
) -> Dict[str, Any]:
    """Compute sliding window statistics for state transitions.

    Returns per-entity metrics: transition count, rate, state distribution,
    most recent state, velocity (transitions per hour).
    """
    with _lock:
        cutoff = _time.time() - window_hours * 3600

        where = "domain_id = ? AND timestamp >= ?"
        params: list = [domain_id, cutoff]
        if entity_name:
            where += " AND entity_name = ?"
            params.append(entity_name)
        if class_name:
            where += " AND class_name = ?"
            params.append(class_name)

        # Transition count
        count_row = _conn.execute(
            f"SELECT COUNT(*) FROM state_changes WHERE {where}", params
        ).fetchone()
        total = count_row[0] if count_row else 0

        # Velocity (transitions per hour)
        velocity = round(total / window_hours, 2) if window_hours > 0 else 0

        # State distribution
        dist_rows = _conn.execute(
            f"SELECT to_state, COUNT(*) as cnt FROM state_changes WHERE {where} "
            f"GROUP BY to_state ORDER BY cnt DESC LIMIT 10", params
        ).fetchall()

        # Most recent transition
        latest = _conn.execute(
            f"SELECT entity_name, from_state, to_state, trigger_type, timestamp "
            f"FROM state_changes WHERE {where} ORDER BY timestamp DESC LIMIT 1", params
        ).fetchone()

        # Transition sequences (chains of 2+ transitions close in time)
        chain_rows = _conn.execute(
            f"SELECT entity_name, COUNT(*) as chain_len FROM state_changes "
            f"WHERE {where} GROUP BY entity_name HAVING chain_len >= 2 ORDER BY chain_len DESC LIMIT 10",
            params
        ).fetchall()

        return {
            "domain_id": domain_id,
            "entity_name": entity_name or "(all)",
            "class_name": class_name or "(all)",
            "window_hours": window_hours,
            "total_transitions": total,
            "velocity": velocity,
            "state_distribution": [
                {"state": r[0], "count": r[1]} for r in dist_rows
            ],
            "latest": {
                "entity_name": latest[0] if latest else "",
                "from_state": latest[1] if latest else "",
                "to_state": latest[2] if latest else "",
                "trigger_type": latest[3] if latest else "",
                "timestamp": latest[4] if latest else 0,
            } if latest else None,
            "top_chains": [
                {"entity_name": r[0], "transitions": r[1]} for r in chain_rows
            ],
        }


def get_domain_transition_rate(
    domain_id: str,
    *,
    window_hours: float = 24.0,
    bucket_minutes: int = 60,
) -> List[Dict[str, Any]]:
    """Compute transition rate over time, bucketed by interval.

    Useful for: detecting acceleration, mutation points, burst periods.
    """
    with _lock:
        cutoff = _time.time() - window_hours * 3600
        bucket_secs = bucket_minutes * 60
        num_buckets = int(window_hours * 3600 / bucket_secs)

        rows = _conn.execute(
            """SELECT timestamp FROM state_changes
               WHERE domain_id = ? AND timestamp >= ?
               ORDER BY timestamp""",
            (domain_id, cutoff),
        ).fetchall()

        if not rows:
            return []

        t0 = rows[0][0]
        buckets: dict = {}
        for (ts,) in rows:
            idx = int((ts - t0) / bucket_secs)
            buckets[idx] = buckets.get(idx, 0) + 1

        result = []
        for i in range(num_buckets + 1):
            count = buckets.get(i, 0)
            result.append({
                "bucket_index": i,
                "time_offset_hours": round(i * bucket_minutes / 60, 1),
                "transition_count": count,
            })
        return result


def get_state_distribution(
    domain_id: str,
    *,
    class_name: str = "",
) -> Dict[str, Any]:
    """Get current state distribution across all entities in a domain."""
    with _lock:
        where = "domain_id = ?"
        params: list = [domain_id]
        if class_name:
            where += " AND class_name = ?"
            params.append(class_name)

        # Latest state per entity (subquery by max timestamp)
        rows = _conn.execute(
            f"""SELECT sc.to_state, COUNT(*) as cnt FROM state_changes sc
                INNER JOIN (
                    SELECT entity_name, MAX(timestamp) as max_ts
                    FROM state_changes WHERE {where}
                    GROUP BY entity_name
                ) latest ON sc.entity_name = latest.entity_name AND sc.timestamp = latest.max_ts
                WHERE {where}
                GROUP BY sc.to_state ORDER BY cnt DESC""",
            params + params,
        ).fetchall()

        distribution = {r[0]: r[1] for r in rows}
        total = sum(distribution.values())

        return {
            "domain_id": domain_id,
            "class_name": class_name or "(all)",
            "total_entities": total,
            "distribution": distribution,
            "most_common_state": max(distribution, key=distribution.get) if distribution else "",
        }


def record_feedback(
    session_id: str = "",
    query_text: str = "",
    rating: int = 0,
    is_helpful: Optional[bool] = None,
    domain_id: str = "default",
) -> None:
    """Record user feedback on an answer."""
    with _lock:
        _conn.execute(
            """INSERT INTO feedback (session_id, query_text, rating, is_helpful, domain_id, timestamp)
               VALUES (?,?,?,?,?,?)""",
            (session_id, query_text, rating, int(is_helpful) if is_helpful is not None else None,
             domain_id, _time.time()),
        )
        _conn.commit()


def get_feedback_stats(domain_id: str = "default") -> Dict[str, Any]:
    """Get aggregated feedback statistics."""
    with _lock:
        total = _conn.execute(
            "SELECT COUNT(*) FROM feedback WHERE domain_id=?", (domain_id,)
        ).fetchone()[0]
        helpful = _conn.execute(
            "SELECT COUNT(*) FROM feedback WHERE domain_id=? AND is_helpful=1", (domain_id,)
        ).fetchone()[0]
        avg_rating = _conn.execute(
            "SELECT AVG(rating) FROM feedback WHERE domain_id=? AND rating > 0", (domain_id,)
        ).fetchone()[0] or 0
        recent = _conn.execute(
            "SELECT query_text, rating, is_helpful, timestamp FROM feedback WHERE domain_id=? ORDER BY timestamp DESC LIMIT 10",
            (domain_id,),
        ).fetchall()
        return {
            "domain_id": domain_id,
            "total": total,
            "helpful_count": helpful,
            "helpful_rate": round(helpful / total, 3) if total > 0 else 0,
            "avg_rating": round(avg_rating, 2),
            "recent": [
                {"query": r[0][:60], "rating": r[1], "is_helpful": bool(r[2]) if r[2] is not None else None, "timestamp": r[3]}
                for r in recent
            ],
        }


def get_feedback_driven_thresholds(
    domain_id: str = "default",
    *,
    base_threshold: float = 0.5,
    min_samples: int = 5,
) -> Dict[str, float]:
    """L5 continuous learning: adjust thresholds based on feedback.

    High satisfaction (>0.8) → more permissive (lower threshold)
    Low satisfaction (<0.4) → more strict (higher threshold)
    """
    with _lock:
        rows = _conn.execute(
            """SELECT sc.class_name, AVG(f.is_helpful) as sat, COUNT(*) as cnt
               FROM feedback f
               INNER JOIN state_changes sc ON sc.domain_id = f.domain_id
               WHERE f.domain_id = ? AND f.is_helpful IS NOT NULL
               GROUP BY sc.class_name HAVING cnt >= ?""",
            (domain_id, min_samples),
        ).fetchall()
        thresholds: Dict[str, float] = {}
        for class_name, satisfaction, count in rows:
            if satisfaction is None: continue
            if satisfaction >= 0.8:
                adjusted = max(0.3, base_threshold - 0.1)
            elif satisfaction <= 0.4:
                adjusted = min(0.8, base_threshold + 0.15)
            else:
                adjusted = base_threshold
            thresholds[class_name] = round(adjusted, 3)
        return thresholds
