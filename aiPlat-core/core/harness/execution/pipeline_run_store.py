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

                -- ── P2-A1: append-only event log (event-sourced complement) ──
                CREATE TABLE IF NOT EXISTS pipeline_run_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    stage_id TEXT NOT NULL DEFAULT '',
                    payload TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_run_events_run
                    ON pipeline_run_events(run_id, seq);
            """)
            # ── v3.1 migration: HITL fields (idempotent — ignore if already exist) ──
            for col, col_type in [
                ("_hitl_stage_id", "TEXT DEFAULT ''"),
                ("_hitl_phase_name", "TEXT DEFAULT ''"),
                ("_hitl_output_artifact", "TEXT DEFAULT ''"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE pipeline_runs ADD COLUMN {col} {col_type}")
                except Exception:
                    pass  # noqa: schema-idempotent
            # ── v3.2: full stage config persistence (for restart recovery) ──
            for col, col_type in [
                ("output_artifact", "TEXT DEFAULT ''"),
                ("hitl", "INTEGER DEFAULT 0"),
                ("hitl_phase", "TEXT DEFAULT ''"),
                ("agent_name", "TEXT DEFAULT ''"),
                ("input_artifacts", "TEXT DEFAULT ''"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE pipeline_stages ADD COLUMN {col} {col_type}")
                except Exception:
                    pass  # noqa: schema-idempotent
            # ── v3.3: cross-worker HITL signal ──
            try:
                conn.execute("ALTER TABLE pipeline_runs ADD COLUMN _hitl_action TEXT DEFAULT ''")
            except Exception:
                pass  # noqa: schema-idempotent
            # ── v3.4: clear inline artifact data — now stored in filesystem ──
            conn.execute(
                "UPDATE pipeline_stages SET artifact_output = '' "
                "WHERE LENGTH(artifact_output) > 200 AND artifact_output NOT LIKE '/%'"
            )
            # ── v3.5: _progress persistence for frontend stage tracking ──
            try:
                conn.execute("ALTER TABLE pipeline_runs ADD COLUMN _progress_json TEXT DEFAULT ''")
            except Exception:
                pass  # noqa: schema-idempotent
            # ── v3.6: output_dir persistence (survive restart → artifact file paths) ──
            try:
                conn.execute("ALTER TABLE pipeline_runs ADD COLUMN output_dir TEXT DEFAULT ''")
            except Exception:
                pass  # noqa: schema-idempotent
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

    # ── P2-A1: append-only event log (event-sourced complement) ──

    def append_run_event(self, run_id: str, event_type: str, stage_id: str = "",
                         payload: Optional[Dict[str, Any]] = None) -> None:
        """Append an event to the run's append-only log (P2-A1).

        Event types: stage_started / stage_completed / stage_skipped /
        stage_paused / stage_failed / hitl_requested / hitl_resolved /
        run_phase_changed / pipeline_started / pipeline_finished.
        Payload is JSON-serialized. Never mutates existing rows —
        run current state remains in pipeline_runs (state+event dual-write).
        """
        import json as _json
        self._execute(
            """INSERT INTO pipeline_run_events
               (run_id, event_type, stage_id, payload, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (run_id, event_type, stage_id,
             _json.dumps(payload or {}, ensure_ascii=False),
             _time.time()),
        )

    def list_run_events(self, run_id: str, limit: int = 500) -> List[Dict[str, Any]]:
        """Read back events in append order (for replay / UI timeline)."""
        import json as _json
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT seq, run_id, event_type, stage_id, payload, created_at
                   FROM pipeline_run_events WHERE run_id = ?
                   ORDER BY seq ASC LIMIT ?""",
                (run_id, int(limit)),
            ).fetchall()
        finally:
            conn.close()
        out = []
        for r in rows or []:
            try:
                payload = _json.loads(r[4]) if r[4] else {}
            except Exception:  # noqa: BLE001
                payload = {}
            out.append({
                "seq": r[0], "run_id": r[1], "event_type": r[2],
                "stage_id": r[3], "payload": payload, "created_at": r[5],
            })
        return out

    def replay_run_events(self, run_id: str) -> Optional[Dict[str, Any]]:
        """P2-A1 phase 2: fold the append-only event log into a run state snapshot.

        Derived (event-sourced) view — the *source of truth* for audit/replay.
        The pipeline_runs row remains the fast-path state cache (dual-write);
        this method reconstructs phase / current_stage_idx / pass_rate purely
        from events, so consumers can cross-check or rebuild after a crash.
        Returns None when no events exist for the run.
        """
        evs = self.list_run_events(run_id, limit=5000)
        if not evs:
            return None

        phase = "executing"
        current_stage_idx = 0
        pass_rate = 0.0
        stage_ids: List[str] = []
        terminal = {"pipeline_finished", "pipeline_failed", "pipeline_cancelled", "pipeline_paused"}
        terminal_phase = {"pipeline_finished": "done", "pipeline_failed": "failed",
                          "pipeline_cancelled": "cancelled", "pipeline_paused": "paused"}
        hitl_state_name = "review"  # mapped state for pipeline_hitl (not a business concept)
        last_terminal = ""

        for e in evs:
            evt = e.get("event_type", "")
            payload = e.get("payload") or {}
            if evt == "pipeline_started":
                phase = "executing"
            elif evt == "pipeline_forked":
                # Fork 会话：继承分叉点状态（事件源纯度——子 run 状态可从自身事件重建）
                phase = "executing"
                current_stage_idx = int(payload.get("current_stage_idx") or current_stage_idx)
                try:
                    pass_rate = float(payload.get("pass_rate") or pass_rate)
                except (TypeError, ValueError):
                    pass  # noqa: schema-idempotent
            elif evt in terminal:
                last_terminal = evt
                phase = terminal_phase[evt]
                # Terminal events carry the final progress too
                current_stage_idx = int(payload.get("current_stage_idx") or current_stage_idx)
                try:
                    pass_rate = float(payload.get("pass_rate") or pass_rate)
                except (TypeError, ValueError):
                    pass  # noqa: schema-idempotent
            elif evt == "pipeline_hitl":
                phase = hitl_state_name
            elif evt == "pipeline_progress":
                phase = payload.get("phase") or phase
                current_stage_idx = int(payload.get("current_stage_idx") or current_stage_idx)
                try:
                    pass_rate = float(payload.get("pass_rate") or pass_rate)
                except (TypeError, ValueError):
                    pass  # noqa: schema-idempotent
            if e.get("stage_id"):
                if e["stage_id"] not in stage_ids:
                    stage_ids.append(e["stage_id"])

        return {
            "run_id": run_id,
            "phase": phase,
            "current_stage_idx": current_stage_idx,
            "pass_rate": pass_rate,
            "stages_visited": stage_ids,
            "event_count": len(evs),
            "last_terminal_event": last_terminal or None,
            "derived": True,  # marker: this is the event-sourced view
        }

    def fork_run_from_events(
        self,
        source_run_id: str,
        new_run_id: str,
        project_id: str = "",
        *,
        note: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Fork a new run from an existing run's event log (DSH fork / Codex thread/fork aligned).

        Event-sourced fork: folds the source run's events (replay_run_events)
        into a derived state, then creates a new pipeline_runs row initialized
        from that state. The new run inherits the source's stage progress /
        pass_rate / phase, and records a ``parent_run_id`` in its events so the
        fork lineage is traceable (parent_run_id → child fork).

        Returns the new run's folded state, or None when the source has no
        events (nothing to fork).
        """
        folded = self.replay_run_events(source_run_id)
        if folded is None:
            return None
        import json as _json
        import time as _time_fork
        # 新 run 记录：继承源 run 的进度/通过率，phase 归位 executing（从分叉点继续）
        now = str(_time_fork.time())
        self._execute(
            """INSERT OR REPLACE INTO pipeline_runs
               (run_id, project_id, phase, current_stage_idx, total_stages,
                tokens_used, tokens_budget, pass_rate, error_message,
                started_at, finished_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                new_run_id, project_id or "", "executing",
                int(folded.get("current_stage_idx") or 0),
                int(folded.get("stages_visited") and len(folded["stages_visited"]) or 0),
                int(folded.get("tokens_used") or 0),
                int(folded.get("tokens_budget") or 0),
                float(folded.get("pass_rate") or 0.0),
                "", now, "", now,
            ),
        )
        # 事件溯源：fork 血缘写入新 run 的事件日志（append-only，不污染源）。
        # pipeline_forked 携带继承的分叉点状态（current_stage_idx / pass_rate），
        # 使新 run 的状态可纯从自身事件日志重建（replay_run_events 会折叠该事件）。
        self.append_run_event(
            new_run_id, "pipeline_forked",
            payload={"parent_run_id": source_run_id,
                     "note": note or "forked from event replay",
                     "source_event_count": int(folded.get("event_count") or 0),
                     "current_stage_idx": int(folded.get("current_stage_idx") or 0),
                     "pass_rate": float(folded.get("pass_rate") or 0.0)},
        )
        return folded

    def list_forked_runs(self, parent_run_id: str, limit: int = 50) -> List[str]:
        """List run_ids forked from a given parent (fork lineage query)."""
        rows = self._get_conn().execute(
            """SELECT run_id FROM pipeline_run_events
               WHERE event_type = 'pipeline_forked'
                 AND json_extract(payload, '$.parent_run_id') = ?
               ORDER BY seq DESC LIMIT ?""",
            (parent_run_id, limit),
        ).fetchall()
        return [r[0] for r in rows]

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

    # ── v3.2: Atomic phase + HITL update (single SQL transaction) ──────

    def atomic_update_phase_and_hitl(
        self,
        run_id: str,
        phase: str,
        current_stage_idx: int = 0,
        pass_rate: float = 0.0,
        hitl_stage_id: str = "",
        hitl_phase_name: str = "",
        hitl_output_artifact: str = "",
        error: str = "",
        _progress_json: str = "",
        output_dir: str = "",
    ) -> None:
        """Update phase + HITL fields + progress + pipeline run in a single atomic SQL statement.
        
        Replaces the old pattern of calling update_run_progress →
        update_run_phase → update_hitl_fields in three separate transactions
        (which could leave the DB in an inconsistent state if one failed).
        """
        now = _time.strftime("%Y-%m-%dT%H:%M:%S")
        finished = now if phase in ("done", "failed", "cancelled", "expired") else ""
        self._execute(
            """UPDATE pipeline_runs
               SET phase = ?, error_message = ?, finished_at = ?,
                   current_stage_idx = ?, pass_rate = ?,
                   _hitl_stage_id = ?, _hitl_phase_name = ?,
                   _hitl_output_artifact = ?, _progress_json = ?,
                   output_dir = CASE WHEN ? != '' THEN ? ELSE output_dir END,
                   updated_at = ?
               WHERE run_id = ?""",
            (phase, error, finished, current_stage_idx, pass_rate,
             hitl_stage_id, hitl_phase_name, hitl_output_artifact, _progress_json,
             output_dir, output_dir, now, run_id),
        )

    # ── v3.1: HITL field writers ───────────────────────────────────

    def update_hitl_fields(
        self,
        run_id: str,
        hitl_stage_id: str = "",
        hitl_phase_name: str = "",
        hitl_output_artifact: str = "",
    ) -> None:
        """Write precise HITL pause location for frontend visibility."""
        now = _time.strftime("%Y-%m-%dT%H:%M:%S")
        self._execute(
            """UPDATE pipeline_runs
               SET _hitl_stage_id = ?, _hitl_phase_name = ?,
                   _hitl_output_artifact = ?, updated_at = ?
               WHERE run_id = ?""",
            (hitl_stage_id, hitl_phase_name, hitl_output_artifact, now, run_id),
        )

    def clear_hitl_fields(self, run_id: str) -> None:
        """Clear HITL fields when pipeline resumes."""
        now = _time.strftime("%Y-%m-%dT%H:%M:%S")
        self._execute(
            """UPDATE pipeline_runs
               SET _hitl_stage_id = '', _hitl_phase_name = '',
                   _hitl_output_artifact = '', _hitl_action = '',
                   updated_at = ?
               WHERE run_id = ?""",
            (now, run_id),
        )

    # ── v3.3: Cross-worker HITL (DB-signalled approve/reject) ──

    def write_hitl_action(self, project_id: str, action: str) -> bool:
        """Write a HITL action to the latest paused pipeline for a project.

        Returns True if updated, False if no paused pipeline found.
        """
        now = _time.strftime("%Y-%m-%dT%H:%M:%S")
        conn = self._get_conn()
        try:
            conn.execute(
                """UPDATE pipeline_runs
                   SET _hitl_action = ?, updated_at = ?
                   WHERE run_id = (
                       SELECT run_id FROM pipeline_runs
                       WHERE project_id = ? AND phase = 'paused'
                       ORDER BY updated_at DESC LIMIT 1
                   )""",
                (action, now, project_id),
            )
            conn.commit()
            return conn.total_changes > 0
        finally:
            conn.close()

    def poll_hitl_action(self, run_id: str) -> str:
        """Check for a pending HITL action on a specific run."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT _hitl_action FROM pipeline_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            return (row["_hitl_action"] or "") if row else ""
        finally:
            conn.close()

    def clear_hitl_action(self, run_id: str) -> None:
        """Clear the HITL action flag after processing."""
        self._execute(
            "UPDATE pipeline_runs SET _hitl_action = '' WHERE run_id = ?",
            (run_id,),
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
        output_artifact: str = "",
        hitl: bool = False,
        hitl_phase: str = "",
        agent_name: str = "",
        input_artifacts: str = "",
    ) -> None:
        progress_str = json.dumps(progress) if progress else ""
        now = _time.strftime("%Y-%m-%dT%H:%M:%S")
        started = now if status in ("running",) else ""
        finished = now if status in ("completed", "failed", "skipped") else ""

        self._execute(
            """INSERT INTO pipeline_stages
               (run_id, stage_id, stage_idx, agent_id, skill_name,
                status, progress_json, artifact_key, artifact_output,
                elapsed_sec, error_message, started_at, finished_at,
                output_artifact, hitl, hitl_phase, agent_name, input_artifacts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?)
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
                END,
                output_artifact = excluded.output_artifact,
                hitl = excluded.hitl,
                hitl_phase = excluded.hitl_phase,
                agent_name = excluded.agent_name,
                input_artifacts = excluded.input_artifacts""",
            (
                run_id, stage_id, stage_idx, agent_id, skill_name,
                status, progress_str, artifact_key, artifact_output,
                elapsed_sec, error_message, started, finished,
                output_artifact, 1 if hitl else 0, hitl_phase, agent_name, input_artifacts,
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
            # ── v3.6: output_dir (persisted so artifact file paths survive restart) ──
            "output_dir": run.get("output_dir", "") or "",
            # ── v3.1: HITL precise pause location ──
            "_hitl_stage_id": run.get("_hitl_stage_id", "") or "",
            "_hitl_phase_name": run.get("_hitl_phase_name", "") or "",
            "_hitl_output_artifact": run.get("_hitl_output_artifact", "") or "",
        }

        # Merge stage artifacts + progress into state
        import os as _os_fs
        _progress = None
        _out_dir = run.get("output_dir", "") or ""
        for s in stages:
            if s["artifact_key"]:
                # Read from filesystem if artifact_output is a file path
                _content = s["artifact_output"]
                if _content and _os_fs.path.isfile(_content):
                    try:
                        with open(_content, "r", encoding="utf-8") as _f:
                            _content = _f.read()
                    except Exception:
                        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)  # fallback: use raw path string
                if not _content and _out_dir:
                    # Fallback: artifact_output lost (e.g. broken recovery) — read from output dir file
                    _fallback = _os_fs.path.join(_out_dir, f"{s['artifact_key']}.json")
                    if _os_fs.path.isfile(_fallback):
                        try:
                            with open(_fallback, "r", encoding="utf-8") as _f:
                                _content = _f.read()
                        except Exception:
                            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
                if _content:
                    state[s["artifact_key"]] = {
                        "raw_output": _content,
                        "elapsed_sec": s["elapsed_sec"],
                    }
            # Restore health reports from progress_json
            if s["artifact_key"] and s["artifact_key"].startswith("_health_report_"):
                if s["progress_json"]:
                    try:
                        state[s["artifact_key"]] = json.loads(s["progress_json"])
                    except json.JSONDecodeError:  # noqa: best-effort-parse
                        pass
            if s["progress_json"]:
                try:
                    p = json.loads(s["progress_json"])
                    if p and p.get("status") in ("running",):
                        _progress = p  # running stage wins
                    elif p and _progress is None:
                        _progress = p  # first non-running as fallback
                except json.JSONDecodeError:  # noqa: best-effort-parse
                    pass

        # Restore _progress from runs table (v3.5 — persisted per stage start)
        _run_progress = run.get("_progress_json", "")
        if _run_progress and not _progress:
            try:
                _progress = json.loads(_run_progress)
            except json.JSONDecodeError:  # noqa: best-effort-parse
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
        run = dict(run)  # sqlite3.Row → dict so .get() works below

        stages = self.get_stages(run_id)
        import os as _os_fs2
        _output_dir = run.get("output_dir", "") or ""
        state: Dict[str, Any] = {
            "phase": run["phase"],
            "_current_stage_idx": run["current_stage_idx"],
            "tokens_used": run["tokens_used"],
            "tokens_budget": run["tokens_budget"],
            "pass_rate": run["pass_rate"],
            "error": run["error_message"],
            "session_id": run["run_id"],
            # ── v3.6: output_dir persisted to run record (engine._output_root wrote it) ──
            "output_dir": _output_dir,
            # ── v3.1: HITL precise pause location (must survive restart) ──
            "_hitl_stage_id": run.get("_hitl_stage_id", "") or "",
            "_hitl_phase_name": run.get("_hitl_phase_name", "") or "",
            "_hitl_output_artifact": run.get("_hitl_output_artifact", "") or "",
        }
        _progress = None
        for s in stages:
            if s["artifact_key"]:
                _content = s["artifact_output"]
                if _content and _os_fs2.path.isfile(_content):
                    try:
                        with open(_content, "r", encoding="utf-8") as _f:
                            _content = _f.read()
                    except Exception:
                        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
                if not _content and _output_dir:
                    # Fallback: artifact_output lost — read from output dir file
                    _fallback = _os_fs2.path.join(_output_dir, f"{s['artifact_key']}.json")
                    if _os_fs2.path.isfile(_fallback):
                        try:
                            with open(_fallback, "r", encoding="utf-8") as _f:
                                _content = _f.read()
                        except Exception:
                            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
                if _content:
                    state[s["artifact_key"]] = {
                        "raw_output": _content,
                        "elapsed_sec": s["elapsed_sec"],
                    }
            if s["progress_json"]:
                try:
                    p = json.loads(s["progress_json"])
                    if p and p.get("status") in ("running",):
                        _progress = p
                    elif p and _progress is None:
                        _progress = p
                except json.JSONDecodeError:  # noqa: best-effort-parse
                    pass

        _run_progress = run.get("_progress_json", "")
        if _run_progress and not _progress:
            try:
                _progress = json.loads(_run_progress)
            except json.JSONDecodeError:  # noqa: best-effort-parse
                pass

        if _progress:
            state["_progress"] = _progress
        # ── P2-A1 phase 3: event-sourced cross-check (state ↔ event consistency) ──
        try:
            derived = self.replay_run_events(run_id)
            if derived:
                state["event_derived"] = derived
                # Consistency: snapshot phase should match folded event phase
                _consistent = (state.get("phase") == derived.get("phase"))
                state["state_event_consistent"] = _consistent
                if not _consistent:
                    # P3-1: dual-track drift must be visible (upgraded from debug-only).
                    # Read path stays side-effect free (no event-table write here);
                    # a transient write-order window can produce this, so it is a
                    # WARNING (not an error) — visible to diagnostics, never blocks.
                    logging.getLogger(__name__).warning(
                        "run state/event drift: run_id=%s snapshot_phase=%r event_phase=%r",
                        run_id, state.get("phase"), derived.get("phase"),
                    )
        except Exception as _e:  # noqa: BLE001
            logging.getLogger(__name__).debug("replay cross-check failed: %s", _e)
        return state

    # ── Recovery ─────────────────────────────────────────────────

    def list_paused_runs(self) -> List[Dict[str, Any]]:
        """Return runs stuck in paused/HITL state (for restart recovery)."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT * FROM pipeline_runs
                   WHERE phase = 'paused'"""
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def load_stages_config(self, run_id: str) -> List[Dict[str, Any]]:
        """Load full stage config from pipeline_stages for engine reconstruction."""
        return self.get_stages(run_id)

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
