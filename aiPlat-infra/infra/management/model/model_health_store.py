"""
ModelHealthStore — persistent model health tracking for adaptive selection.

Tracks per-model success/failure counts, latency, and business outcome
scores in SQLite. Survives process restarts. Consumed by _score_model
for dynamic model ranking.

Single writer: generate_with_fallback records after each LLM call.
Reader: _calculate_dynamic_boost in manager.py.
Business feedback: kpi_tracker.py writes business_score from pipeline pass rates.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time as _time
from functools import wraps
from typing import Any, Dict, Optional

_log = logging.getLogger("infra.model.health")

_DB_PATH = os.environ.get(
    "AIPLAT_MODEL_HEALTH_DB",
    os.path.expanduser("~/.aiplat/aiplat_executions.sqlite3")
)
_BUSY_TIMEOUT_MS = 5000


def _retry_on_busy(max_attempts: int = 3, wait_ms: int = 100):
    """Retry decorator for SQLITE_BUSY errors."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_err = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "busy" in str(e).lower() or "locked" in str(e).lower():
                        last_err = e
                        if attempt < max_attempts - 1:
                            _time.sleep(wait_ms / 1000.0)
                        continue
                    raise
            raise last_err  # type: ignore[misc]

        return wrapper

    return decorator


class ModelHealthStore:
    """SQLite-backed model health tracker.

    Usage:
        store = ModelHealthStore()
        store.record_success("example-model", latency_ms=1200, purpose="chat")
        store.record_failure("example-model", error="404")

        health = store.get_health_score("example-model")
        # → {"success_count": 10, "failure_count": 2, "call_count": 12,
        #    "avg_latency_ms": 1100.0, "business_score": 0.85}
    """

    def __init__(self, db_path: str = _DB_PATH):
        self._db_path = db_path
        self._ensure_db()

    def _get_conn(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS};")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    @_retry_on_busy(max_attempts=3, wait_ms=100)
    def _execute(self, sql: str, params: tuple = ()) -> None:
        conn = self._get_conn()
        try:
            conn.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    def _ensure_db(self) -> None:
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS model_health (
                    model_name TEXT PRIMARY KEY,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    total_latency_ms REAL DEFAULT 0,
                    call_count INTEGER DEFAULT 0,
                    business_score REAL DEFAULT 0.5,
                    last_success_at TEXT,
                    last_failure_at TEXT,
                    last_error_msg TEXT,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS model_health_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_name TEXT,
                    success BOOLEAN,
                    latency_ms REAL,
                    error_msg TEXT,
                    purpose TEXT,
                    recorded_at TEXT
                );
            """)
            conn.commit()
        finally:
            conn.close()

    # ── Record operations ────────────────────────────────────────

    def record_success(
        self,
        model_name: str,
        *,
        latency_ms: float = 0.0,
        purpose: str = "",
    ) -> None:
        now = _time.strftime("%Y-%m-%dT%H:%M:%S")
        self._execute(
            """INSERT INTO model_health_history
               (model_name, success, latency_ms, purpose, recorded_at)
               VALUES (?, 1, ?, ?, ?)""",
            (model_name, latency_ms, purpose, now),
        )
        self._execute(
            """INSERT INTO model_health (model_name, success_count, total_latency_ms,
               call_count, last_success_at, updated_at)
               VALUES (?, 1, ?, 1, ?, ?)
               ON CONFLICT(model_name) DO UPDATE SET
                success_count = success_count + 1,
                total_latency_ms = total_latency_ms + ?,
                call_count = call_count + 1,
                last_success_at = ?,
                updated_at = ?""",
            (model_name, latency_ms, now, now, latency_ms, now, now),
        )

    def record_failure(
        self,
        model_name: str,
        error: str = "",
        *,
        purpose: str = "",
    ) -> None:
        now = _time.strftime("%Y-%m-%dT%H:%M:%S")
        self._execute(
            """INSERT INTO model_health_history
               (model_name, success, error_msg, purpose, recorded_at)
               VALUES (?, 0, ?, ?, ?)""",
            (model_name, error[:500], purpose, now),
        )
        self._execute(
            """INSERT INTO model_health (model_name, failure_count, call_count,
               last_failure_at, last_error_msg, updated_at)
               VALUES (?, 1, 1, ?, ?, ?)
               ON CONFLICT(model_name) DO UPDATE SET
                failure_count = failure_count + 1,
                call_count = call_count + 1,
                last_failure_at = ?,
                last_error_msg = ?,
                updated_at = ?""",
            (model_name, now, error[:500], now, now, error[:500], now),
        )

    def set_business_score(self, model_name: str, score: float) -> None:
        now = _time.strftime("%Y-%m-%dT%H:%M:%S")
        self._execute(
            """INSERT INTO model_health (model_name, business_score, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(model_name) DO UPDATE SET
                business_score = ?,
                updated_at = ?""",
            (model_name, score, now, score, now),
        )

    # ── Query operations ──────────────────────────────────────────

    def get_health_score(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Return health dict or None if no records exist (cold start)."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                """SELECT success_count, failure_count, total_latency_ms,
                   call_count, business_score
                   FROM model_health WHERE model_name = ?""",
                (model_name,),
            ).fetchone()
            if not row:
                return None
            calls = row[3]
            avg_lat = (row[2] / calls) if calls > 0 else 1000.0
            return {
                "success_count": row[0],
                "failure_count": row[1],
                "total_latency_ms": row[2],
                "call_count": calls,
                "avg_latency_ms": avg_lat,
                "business_score": row[4],
            }
        finally:
            conn.close()

    def list_health_scores(self) -> Dict[str, Dict[str, Any]]:
        """Return health dicts for all tracked models."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT model_name, success_count, failure_count,
                   total_latency_ms, call_count, business_score
                   FROM model_health"""
            ).fetchall()
            result = {}
            for r in rows:
                calls = r[4]
                avg_lat = (r[3] / calls) if calls > 0 else 1000.0
                result[r[0]] = {
                    "success_count": r[1],
                    "failure_count": r[2],
                    "total_latency_ms": r[3],
                    "call_count": calls,
                    "avg_latency_ms": avg_lat,
                    "business_score": r[5],
                }
            return result
        finally:
            conn.close()


# ── Module-level singleton ───────────────────────────────────────

_store: Optional[ModelHealthStore] = None


def get_model_health_store() -> ModelHealthStore:
    global _store
    if _store is None:
        _store = ModelHealthStore()
    return _store
