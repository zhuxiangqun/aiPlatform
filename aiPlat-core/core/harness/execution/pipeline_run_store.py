"""
PipelineRunStore — single source of truth for pipeline state.

Replaces the fragmented JSON + dict + SQLite persistence with a
single SQLite database (WAL mode, busy_timeout=5000) that is the
sole writer of pipeline progress.

All write operations include a retry wrapper (3 attempts, 100ms wait)
to handle SQLITE_BUSY from multi-worker concurrent access.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time as _time
from functools import wraps
from typing import Any, Dict, List, Optional

from core.utils.paths import get_aiplat_data_dir

_log = logging.getLogger("aiplat.pipeline.store")

_DB_PATH = os.path.join(get_aiplat_data_dir("data"), "pipeline_runs.db")
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
                    if "database is locked" in str(e).lower() or "busy" in str(e).lower():
                        last_err = e
                        if attempt < max_attempts - 1:
                            _time.sleep(wait_ms / 1000.0)
                        continue
                    raise
            raise last_err  # type: ignore[misc]

        return wrapper

    return decorator


class PipelineRunStore:
    """SQLite-backed pipeline run & stage store.

    Usage:
        store = PipelineRunStore()
        run_id = store.create_run("prj_abc")
        store.update_stage(run_id, "canvas_node_1", stage_idx=0,
                           status="running", progress={"current_step": 3})
    """

    def __init__(self, db_path: str = _DB_PATH):
        self._db_path = db_path
        self._ensure_db()

    # ── Connection management ────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS};")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_db(self) -> None:
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    run_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    phase TEXT NOT NULL DEFAULT 'executing',
                    current_stage_idx INTEGER NOT NULL DEFAULT 0,
                    total_stages INTEGER NOT NULL DEFAULT 0,
                    tokens_used INTEGER NOT NULL DEFAULT 0,
                    tokens_budget INTEGER NOT NULL DEFAULT 0,
                    pass_rate REAL NOT NULL DEFAULT 0.0,
                    error_message TEXT DEFAULT '',
                    started_at TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS pipeline_stages (
                    run_id TEXT NOT NULL,
                    stage_id TEXT NOT NULL,
                    stage_idx INTEGER NOT NULL DEFAULT 0,
                    agent_id TEXT NOT NULL DEFAULT '',
                    skill_name TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    progress_json TEXT NOT NULL DEFAULT '',
                    artifact_key TEXT NOT NULL DEFAULT '',
                    artifact_output TEXT NOT NULL DEFAULT '',
                    elapsed_sec REAL NOT NULL DEFAULT 0.0,
                    error_message TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (run_id, stage_id)
                );

                CREATE INDEX IF NOT EXISTS idx_pipeline_runs_project
                    ON pipeline_runs(project_id);

                CREATE INDEX IF NOT EXISTS idx_pipeline_stages_run
                    ON pipeline_stages(run_id);
            """)
            conn.commit()
        finally:
            conn.close()

    # ── Run-level operations ─────────────────────────────────────

    @_retry_on_busy(max_attempts=3, wait_ms=100)
    def _execute(self, sql: str, params: tuple = ()) -> None:
        conn = self._get_conn()
        try:
            conn.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    def create_run(
        self,
        run_id: str,
        project_id: str,
        total_stages: int = 0,
        tokens_budget: int = 0,
    ) -> None:
        now = _time.strftime("%Y-%m-%dT%H:%M:%S")
        self._execute(
            """INSERT OR REPLACE INTO pipeline_runs
               (run_id, project_id, phase, current_stage_idx, total_stages,
                tokens_budget, started_at, updated_at)
               VALUES (?, ?, 'executing', 0, ?, ?, ?, ?)""",
            (run_id, project_id, total_stages, tokens_budget, now, now),
        )

    def update_run_phase(self, run_id: str, phase: str, error: str = "") -> None:
        now = _time.strftime("%Y-%m-%dT%H:%M:%S")
        finished = now if phase in ("done", "failed", "cancelled") else ""
        self._execute(
            """UPDATE pipeline_runs
               SET phase = ?, error_message = ?, finished_at = ?,
                   updated_at = ?
               WHERE run_id = ?""",
            (phase, error, finished, now, run_id),
        )

    def update_run_progress(
        self,
        run_id: str,
        current_stage_idx: int,
        tokens_used: int = 0,
        pass_rate: float = 0.0,
    ) -> None:
        now = _time.strftime("%Y-%m-%dT%H:%M:%S")
        self._execute(
            """UPDATE pipeline_runs
               SET current_stage_idx = ?, tokens_used = tokens_used + ?,
                   pass_rate = ?, updated_at = ?
               WHERE run_id = ?""",
            (current_stage_idx, tokens_used, pass_rate, now, run_id),
        )

    # ── Stage-level operations ───────────────────────────────────

    def upsert_stage(
        self,
        run_id: str,
        stage_id: str,
        *,
        stage_idx: int = 0,
        agent_id: str = "",
        skill_name: str = "",
        status: str = "pending",
        progress: Optional[Dict[str, Any]] = None,
        artifact_key: str = "",
        artifact_output: str = "",
        elapsed_sec: float = 0.0,
        error_message: str = "",
    ) -> None:
        progress_str = json.dumps(progress) if progress else ""
        now = _time.strftime("%Y-%m-%dT%H:%M:%S")
        started = now if status in ("running",) else ""
        finished = now if status in ("completed", "failed", "skipped") else ""

        self._execute(
            """INSERT INTO pipeline_stages
               (run_id, stage_id, stage_idx, agent_id, skill_name,
                status, progress_json, artifact_key, artifact_output,
                elapsed_sec, error_message, started_at, finished_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(run_id, stage_id) DO UPDATE SET
                stage_idx = excluded.stage_idx,
                agent_id = excluded.agent_id,
                skill_name = excluded.skill_name,
                status = excluded.status,
                progress_json = excluded.progress_json,
                artifact_key = excluded.artifact_key,
                artifact_output = excluded.artifact_output,
                elapsed_sec = excluded.elapsed_sec,
                error_message = excluded.error_message,
                started_at = CASE
                    WHEN excluded.started_at != '' THEN excluded.started_at
                    ELSE pipeline_stages.started_at
                END,
                finished_at = CASE
                    WHEN excluded.finished_at != '' THEN excluded.finished_at
                    ELSE pipeline_stages.finished_at
                END""",
            (
                run_id, stage_id, stage_idx, agent_id, skill_name,
                status, progress_str, artifact_key, artifact_output,
                elapsed_sec, error_message, started, finished,
            ),
        )

    # ── Query operations ─────────────────────────────────────────

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM pipeline_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_run_by_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                """SELECT * FROM pipeline_runs
                   WHERE project_id = ?
                   ORDER BY updated_at DESC LIMIT 1""",
                (project_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_run_by_id(self, run_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM pipeline_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_stages(self, run_id: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT * FROM pipeline_stages
                   WHERE run_id = ? ORDER BY stage_idx""",
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_full_state(self, project_id: str) -> Dict[str, Any]:
        """Return aggregated state for frontend polling.

        Merges the latest run with all its stages into one dict.
        This is the single read path — no JSON files, no dict merging.
        """
        run = self.get_run_by_project(project_id)
        if not run:
            return {"phase": "idle"}

        stages = self.get_stages(run["run_id"])

        # Build state: run-level fields + per-stage artifacts
        state: Dict[str, Any] = {
            "phase": run["phase"],
            "_current_stage_idx": run["current_stage_idx"],
            "tokens_used": run["tokens_used"],
            "tokens_budget": run["tokens_budget"],
            "pass_rate": run["pass_rate"],
            "error": run["error_message"],
            "session_id": run["run_id"],
        }

        # Merge stage artifacts + progress into state
        _progress = None
        for s in stages:
            if s["artifact_key"] and s["artifact_output"]:
                state[s["artifact_key"]] = {
                    "raw_output": s["artifact_output"],
                    "elapsed_sec": s["elapsed_sec"],
                }
            if s["progress_json"]:
                try:
                    p = json.loads(s["progress_json"])
                    if p and p.get("status") in ("running",):
                        _progress = p  # running stage wins
                    elif p and _progress is None:
                        _progress = p  # first non-running as fallback
                except json.JSONDecodeError:
                    pass

        if _progress:
            state["_progress"] = _progress

        return state

    def get_full_state_from_run_id(self, run_id: str) -> Dict[str, Any]:
        """Return aggregated state for a specific run_id (not project_id).

        Used by orphan pipeline recovery to reload state when project_id
        may not be known at the callsite.
        """
        run = self._get_conn().execute(
            "SELECT * FROM pipeline_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if not run:
            return {"phase": "idle"}

        stages = self.get_stages(run_id)
        state: Dict[str, Any] = {
            "phase": run["phase"],
            "_current_stage_idx": run["current_stage_idx"],
            "tokens_used": run["tokens_used"],
            "tokens_budget": run["tokens_budget"],
            "pass_rate": run["pass_rate"],
            "error": run["error_message"],
            "session_id": run["run_id"],
        }
        _progress = None
        for s in stages:
            if s["artifact_key"] and s["artifact_output"]:
                state[s["artifact_key"]] = {
                    "raw_output": s["artifact_output"],
                    "elapsed_sec": s["elapsed_sec"],
                }
            if s["progress_json"]:
                try:
                    p = json.loads(s["progress_json"])
                    if p and p.get("status") in ("running",):
                        _progress = p
                    elif p and _progress is None:
                        _progress = p
                except json.JSONDecodeError:
                    pass
        if _progress:
            state["_progress"] = _progress
        return state

    # ── Recovery ─────────────────────────────────────────────────

    def list_orphan_runs(self) -> List[str]:
        """Return run_ids stuck in non-terminal phases (for crash recovery)."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT run_id FROM pipeline_runs
                   WHERE phase IN ('executing', 'pending')"""
            ).fetchall()
            return [r["run_id"] for r in rows]
        finally:
            conn.close()

    def mark_orphan_for_retry(self, run_id: str) -> None:
        """Reset run phase from 'executing' to allow retry after crash."""
        now = _time.strftime("%Y-%m-%dT%H:%M:%S")
        self._execute(
            """UPDATE pipeline_runs
               SET phase = 'pending', updated_at = ?
               WHERE run_id = ? AND phase = 'executing'""",
            (now, run_id),
        )

    # ── Cleanup ──────────────────────────────────────────────────

    def delete_run(self, run_id: str) -> None:
        self._execute("DELETE FROM pipeline_stages WHERE run_id = ?", (run_id,))
        self._execute("DELETE FROM pipeline_runs WHERE run_id = ?", (run_id,))


# ── Module-level singleton ───────────────────────────────────────

_store: Optional[PipelineRunStore] = None


def get_pipeline_run_store() -> PipelineRunStore:
    global _store
    if _store is None:
        _store = PipelineRunStore()
    return _store
