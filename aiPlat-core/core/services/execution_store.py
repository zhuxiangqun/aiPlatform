"""
ExecutionStore (SQLite)

用于持久化 agent/skill 的执行记录与历史查询。

目标（P0 最小可用）：
- 替代 core/server.py 的全局内存 dict（_agent_executions/_agent_history/_skill_executions）
- 服务重启后仍可查询 execution_id 与 history
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import json
import os
import sqlite3
import time
import uuid
import anyio


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def _json_loads(s: Optional[str]) -> Any:
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return s


@dataclass(frozen=True)
class ExecutionStoreConfig:
    db_path: str
    retention_days: Optional[int] = None
    max_rows_per_entity: Optional[int] = None
    prune_on_start: bool = True
    vacuum_on_prune: bool = False


class ExecutionStore:
    CURRENT_SCHEMA_VERSION = 4

    def __init__(self, config: ExecutionStoreConfig):
        self._config = config
        self._init_once_lock = anyio.Lock()
        self._inited = False

    async def init(self) -> None:
        """Init database and run schema migrations (idempotent)."""
        async with self._init_once_lock:
            if self._inited:
                return

            db_path = self._config.db_path
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

            def _init_sync():
                conn = sqlite3.connect(db_path)
                try:
                    conn.execute("PRAGMA journal_mode=WAL;")
                    conn.execute("PRAGMA foreign_keys=ON;")

                    # Meta tables for schema versioning
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS aiplat_meta (
                          k TEXT PRIMARY KEY,
                          v TEXT NOT NULL
                        );
                        """
                    )
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS schema_migrations (
                          version INTEGER PRIMARY KEY,
                          applied_at REAL NOT NULL
                        );
                        """
                    )

                    cur = conn.execute("SELECT v FROM aiplat_meta WHERE k='schema_version'").fetchone()
                    current = int(cur[0]) if cur else 0

                    def _set_version(ver: int) -> None:
                        conn.execute(
                            "INSERT INTO aiplat_meta(k,v) VALUES('schema_version', ?) "
                            "ON CONFLICT(k) DO UPDATE SET v=excluded.v;",
                            (str(ver),),
                        )
                        conn.execute(
                            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(?, ?);",
                            (ver, time.time()),
                        )

                    # ---- Migration v1: executions tables ----
                    if current < 1:
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS agent_executions (
                              id TEXT PRIMARY KEY,
                              agent_id TEXT NOT NULL,
                              status TEXT NOT NULL,
                              input_json TEXT,
                              output_json TEXT,
                              error TEXT,
                              start_time REAL,
                              end_time REAL,
                              duration_ms INTEGER,
                              created_at REAL NOT NULL
                            );
                            """
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_agent_exec_agent_id_time ON agent_executions(agent_id, start_time DESC);"
                        )

                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS skill_executions (
                              id TEXT PRIMARY KEY,
                              skill_id TEXT NOT NULL,
                              status TEXT NOT NULL,
                              input_json TEXT,
                              output_json TEXT,
                              error TEXT,
                              start_time REAL,
                              end_time REAL,
                              duration_ms INTEGER,
                              user_id TEXT,
                              created_at REAL NOT NULL
                            );
                            """
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_skill_exec_skill_id_time ON skill_executions(skill_id, start_time DESC);"
                        )
                        _set_version(1)
                        current = 1

                    # ---- Migration v2: graph runs + checkpoints ----
                    if current < 2:
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS graph_runs (
                              run_id TEXT PRIMARY KEY,
                              graph_name TEXT NOT NULL,
                              status TEXT,
                              start_time REAL NOT NULL,
                              end_time REAL,
                              duration_ms REAL,
                              trace_id TEXT,
                              initial_state_json TEXT,
                              final_state_json TEXT,
                              summary_json TEXT
                            );
                            """
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_graph_runs_name_time ON graph_runs(graph_name, start_time DESC);"
                        )
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS graph_checkpoints (
                              checkpoint_id TEXT PRIMARY KEY,
                              run_id TEXT NOT NULL,
                              step INTEGER NOT NULL,
                              state_json TEXT NOT NULL,
                              created_at REAL NOT NULL,
                              FOREIGN KEY(run_id) REFERENCES graph_runs(run_id) ON DELETE CASCADE
                            );
                            """
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_graph_ckpt_run_step ON graph_checkpoints(run_id, step);"
                        )
                        _set_version(2)
                        current = 2

                    # ---- Migration v3: traces + spans ----
                    if current < 3:
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS traces (
                              trace_id TEXT PRIMARY KEY,
                              name TEXT NOT NULL,
                              status TEXT,
                              start_time REAL NOT NULL,
                              end_time REAL,
                              duration_ms REAL,
                              attributes_json TEXT
                            );
                            """
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_traces_time ON traces(start_time DESC);"
                        )
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS spans (
                              span_id TEXT PRIMARY KEY,
                              trace_id TEXT NOT NULL,
                              parent_span_id TEXT,
                              name TEXT NOT NULL,
                              status TEXT,
                              start_time REAL NOT NULL,
                              end_time REAL,
                              duration_ms REAL,
                              attributes_json TEXT,
                              events_json TEXT,
                              FOREIGN KEY(trace_id) REFERENCES traces(trace_id) ON DELETE CASCADE
                            );
                            """
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id);"
                        )
                        _set_version(3)
                        current = 3

                    # ---- Migration v4: resume links + execution<->trace link ----
                    if current < 4:
                        # graph_runs: resume lineage
                        try:
                            conn.execute("ALTER TABLE graph_runs ADD COLUMN parent_run_id TEXT;")
                        except Exception:
                            pass
                        try:
                            conn.execute("ALTER TABLE graph_runs ADD COLUMN resumed_from_checkpoint_id TEXT;")
                        except Exception:
                            pass
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_graph_runs_parent ON graph_runs(parent_run_id);"
                        )

                        # executions: trace link
                        try:
                            conn.execute("ALTER TABLE agent_executions ADD COLUMN trace_id TEXT;")
                        except Exception:
                            pass
                        try:
                            conn.execute("ALTER TABLE skill_executions ADD COLUMN trace_id TEXT;")
                        except Exception:
                            pass
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_agent_exec_trace_id ON agent_executions(trace_id);"
                        )
                        conn.execute(
                            "CREATE INDEX IF NOT EXISTS idx_skill_exec_trace_id ON skill_executions(trace_id);"
                        )

                        _set_version(4)
                        current = 4

                    # ---- Migration v5: graph_runs trace_id index ----
                    if current < 5:
                        # Some DBs were created before trace_id column existed.
                        try:
                            conn.execute("ALTER TABLE graph_runs ADD COLUMN trace_id TEXT;")
                        except Exception:
                            pass
                        conn.execute("CREATE INDEX IF NOT EXISTS idx_graph_runs_trace ON graph_runs(trace_id);")
                        _set_version(5)
                        current = 5

                    # If legacy db exists with tables but without meta, upgrade meta to current
                    if current < self.CURRENT_SCHEMA_VERSION:
                        _set_version(self.CURRENT_SCHEMA_VERSION)

                    # Ensure idempotency indexes exist (even when schema_version already current)
                    try:
                        conn.execute(
                            "CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_runs_resume_unique "
                            "ON graph_runs(parent_run_id, resumed_from_checkpoint_id) "
                            "WHERE resumed_from_checkpoint_id IS NOT NULL;"
                        )
                    except Exception:
                        pass

                    conn.commit()
                finally:
                    conn.close()

            await anyio.to_thread.run_sync(_init_sync)
            self._inited = True

            # Optional retention pruning on start (best effort)
            if self._config.prune_on_start and (self._config.retention_days or self._config.max_rows_per_entity):
                try:
                    await self.prune()
                except Exception:
                    pass

    async def get_schema_version(self) -> int:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> int:
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute("SELECT v FROM aiplat_meta WHERE k='schema_version'").fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def prune(self, now_ts: Optional[float] = None) -> Dict[str, int]:
        """
        清理历史数据（best-effort）。

        - retention_days：按 created_at/start_time 做时间删除
        - max_rows_per_entity：按 start_time/created_at 限制最大行数（每个 agent_id/skill_id/graph_name 维度）
        """
        await self.init()
        db_path = self._config.db_path
        retention_days = self._config.retention_days
        max_rows = self._config.max_rows_per_entity
        now_ts = float(now_ts or time.time())
        cutoff = now_ts - float(retention_days or 0) * 86400.0

        def _sync() -> Dict[str, int]:
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("PRAGMA foreign_keys=ON;")
                deleted = {"agent_executions": 0, "skill_executions": 0, "graph_runs": 0, "graph_checkpoints": 0, "traces": 0, "spans": 0}

                if retention_days is not None:
                    cur = conn.execute("DELETE FROM agent_executions WHERE created_at < ?", (cutoff,))
                    deleted["agent_executions"] += cur.rowcount or 0
                    cur = conn.execute("DELETE FROM skill_executions WHERE created_at < ?", (cutoff,))
                    deleted["skill_executions"] += cur.rowcount or 0
                    cur = conn.execute("DELETE FROM graph_runs WHERE start_time < ?", (cutoff,))
                    deleted["graph_runs"] += cur.rowcount or 0
                    # graph_checkpoints cascades via FK
                    cur = conn.execute("DELETE FROM traces WHERE start_time < ?", (cutoff,))
                    deleted["traces"] += cur.rowcount or 0
                    # spans cascades via FK

                if max_rows is not None and max_rows > 0:
                    # Keep only last N per agent_id
                    conn.execute(
                        """
                        DELETE FROM agent_executions
                        WHERE id IN (
                          SELECT id FROM (
                            SELECT
                              id,
                              ROW_NUMBER() OVER (PARTITION BY agent_id ORDER BY start_time DESC) AS rn
                            FROM agent_executions
                          )
                          WHERE rn > ?
                        )
                        ;
                        """,
                        (int(max_rows),),
                    )
                    # Keep only last N per skill_id
                    conn.execute(
                        """
                        DELETE FROM skill_executions
                        WHERE id IN (
                          SELECT id FROM (
                            SELECT
                              id,
                              ROW_NUMBER() OVER (PARTITION BY skill_id ORDER BY start_time DESC) AS rn
                            FROM skill_executions
                          )
                          WHERE rn > ?
                        )
                        ;
                        """,
                        (int(max_rows),),
                    )
                    # Keep only last N per graph_name (delete runs; cascades checkpoints)
                    conn.execute(
                        """
                        DELETE FROM graph_runs
                        WHERE run_id IN (
                          SELECT run_id FROM (
                            SELECT
                              run_id,
                              ROW_NUMBER() OVER (PARTITION BY graph_name ORDER BY start_time DESC) AS rn
                            FROM graph_runs
                          )
                          WHERE rn > ?
                        )
                        ;
                        """,
                        (int(max_rows),),
                    )
                    # Keep only last N traces overall (no entity dimension yet)
                    conn.execute(
                        """
                        DELETE FROM traces
                        WHERE trace_id IN (
                          SELECT trace_id FROM (
                            SELECT
                              trace_id,
                              ROW_NUMBER() OVER (ORDER BY start_time DESC) AS rn
                            FROM traces
                          )
                          WHERE rn > ?
                        )
                        ;
                        """,
                        (int(max_rows),),
                    )

                conn.commit()
                if self._config.vacuum_on_prune:
                    conn.execute("VACUUM;")
                return deleted
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ==================== Graph (trace/checkpoint) ====================

    async def start_graph_run(
        self,
        graph_name: str,
        run_id: Optional[str] = None,
        initial_state: Optional[Dict[str, Any]] = None,
        start_time: Optional[float] = None,
        parent_run_id: Optional[str] = None,
        resumed_from_checkpoint_id: Optional[str] = None,
    ) -> str:
        await self.init()
        db_path = self._config.db_path
        run_id = run_id or str(uuid.uuid4())
        start_time = float(start_time or time.time())
        initial_state_json = _json_dumps(initial_state or {})
        trace_id = None
        try:
            meta = initial_state.get("metadata") if isinstance((initial_state or {}).get("metadata"), dict) else {}
            trace_id = meta.get("trace_id")
        except Exception:
            trace_id = None

        def _sync():
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO graph_runs(run_id, graph_name, status, start_time, trace_id, initial_state_json, parent_run_id, resumed_from_checkpoint_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                      graph_name=excluded.graph_name,
                      status=excluded.status,
                      start_time=excluded.start_time,
                      trace_id=excluded.trace_id,
                      initial_state_json=excluded.initial_state_json,
                      parent_run_id=excluded.parent_run_id,
                      resumed_from_checkpoint_id=excluded.resumed_from_checkpoint_id;
                    """,
                    (run_id, graph_name, "running", start_time, trace_id, initial_state_json, parent_run_id, resumed_from_checkpoint_id),
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)
        return run_id

    async def finish_graph_run(
        self,
        run_id: str,
        status: str = "completed",
        final_state: Optional[Dict[str, Any]] = None,
        summary: Optional[Dict[str, Any]] = None,
        end_time: Optional[float] = None,
    ) -> None:
        await self.init()
        db_path = self._config.db_path
        end_time = float(end_time or time.time())
        final_state_json = _json_dumps(final_state or {})
        summary_json = _json_dumps(summary or {})
        trace_id = None
        try:
            meta = final_state.get("metadata") if isinstance((final_state or {}).get("metadata"), dict) else {}
            trace_id = meta.get("trace_id")
        except Exception:
            trace_id = None

        def _sync():
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT start_time FROM graph_runs WHERE run_id=?", (run_id,)).fetchone()
                start_time = float(row["start_time"]) if row else end_time
                duration_ms = (end_time - start_time) * 1000.0
                conn.execute(
                    """
                    UPDATE graph_runs
                    SET status=?, end_time=?, duration_ms=?, final_state_json=?, summary_json=?, trace_id=COALESCE(?, trace_id)
                    WHERE run_id=?;
                    """,
                    (status, end_time, duration_ms, final_state_json, summary_json, trace_id, run_id),
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def add_graph_checkpoint(
        self,
        run_id: str,
        step: int,
        state: Dict[str, Any],
        checkpoint_id: Optional[str] = None,
        created_at: Optional[float] = None,
    ) -> str:
        await self.init()
        db_path = self._config.db_path
        checkpoint_id = checkpoint_id or str(uuid.uuid4())
        created_at = float(created_at or time.time())
        state_json = _json_dumps(state or {})

        def _sync():
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO graph_checkpoints(checkpoint_id, run_id, step, state_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(checkpoint_id) DO UPDATE SET
                      run_id=excluded.run_id,
                      step=excluded.step,
                      state_json=excluded.state_json,
                      created_at=excluded.created_at;
                    """,
                    (checkpoint_id, run_id, int(step), state_json, created_at),
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)
        return checkpoint_id

    async def list_graph_checkpoints(self, run_id: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> List[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    """
                    SELECT checkpoint_id, run_id, step, state_json, created_at
                    FROM graph_checkpoints
                    WHERE run_id=?
                    ORDER BY step ASC
                    LIMIT ? OFFSET ?;
                    """,
                    (run_id, int(limit), int(offset)),
                ).fetchall()
                return [
                    {
                        "checkpoint_id": r["checkpoint_id"],
                        "run_id": r["run_id"],
                        "step": r["step"],
                        "state": _json_loads(r["state_json"]),
                        "created_at": r["created_at"],
                    }
                    for r in rows
                ]
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_graph_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM graph_runs WHERE run_id=?", (run_id,)).fetchone()
                if not row:
                    return None
                return {
                    "run_id": row["run_id"],
                    "graph_name": row["graph_name"],
                    "status": row["status"],
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                    "duration_ms": row["duration_ms"],
                    "trace_id": row["trace_id"] if "trace_id" in row.keys() else None,
                    "initial_state": _json_loads(row["initial_state_json"]),
                    "final_state": _json_loads(row["final_state_json"]),
                    "summary": _json_loads(row["summary_json"]),
                    "parent_run_id": row["parent_run_id"] if "parent_run_id" in row.keys() else None,
                    "resumed_from_checkpoint_id": row["resumed_from_checkpoint_id"] if "resumed_from_checkpoint_id" in row.keys() else None,
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_graph_runs(
        self,
        limit: int = 100,
        offset: int = 0,
        graph_name: Optional[str] = None,
        status: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List graph_runs with basic filters."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                clauses = []
                params: list = []
                if graph_name:
                    clauses.append("graph_name=?")
                    params.append(graph_name)
                if status:
                    clauses.append("status=?")
                    params.append(status)
                if trace_id:
                    clauses.append("trace_id=?")
                    params.append(trace_id)
                where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

                total_row = conn.execute(f"SELECT COUNT(*) AS c FROM graph_runs {where_sql}", tuple(params)).fetchone()
                total = int(total_row["c"] if total_row else 0)

                rows = conn.execute(
                    f"""
                    SELECT run_id, graph_name, status, start_time, end_time, duration_ms, trace_id,
                           parent_run_id, resumed_from_checkpoint_id
                    FROM graph_runs
                    {where_sql}
                    ORDER BY start_time DESC
                    LIMIT ? OFFSET ?
                    """,
                    tuple(params + [int(limit), int(offset)]),
                ).fetchall()

                items = []
                for r in rows:
                    items.append(
                        {
                            "run_id": r["run_id"],
                            "graph_name": r["graph_name"],
                            "status": r["status"],
                            "start_time": r["start_time"],
                            "end_time": r["end_time"],
                            "duration_ms": r["duration_ms"],
                            "trace_id": r["trace_id"] if "trace_id" in r.keys() else None,
                            "parent_run_id": r["parent_run_id"],
                            "resumed_from_checkpoint_id": r["resumed_from_checkpoint_id"],
                        }
                    )
                return {"items": items, "total": total}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ==================== Trace ====================

    async def upsert_trace(self, trace: Dict[str, Any]) -> None:
        await self.init()
        db_path = self._config.db_path

        payload = (
            trace.get("trace_id"),
            trace.get("name") or "",
            trace.get("status"),
            float(trace.get("start_time") or time.time()),
            trace.get("end_time"),
            trace.get("duration_ms"),
            _json_dumps(trace.get("attributes") or {}),
        )

        def _sync():
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO traces(trace_id, name, status, start_time, end_time, duration_ms, attributes_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(trace_id) DO UPDATE SET
                      name=excluded.name,
                      status=excluded.status,
                      start_time=excluded.start_time,
                      end_time=excluded.end_time,
                      duration_ms=excluded.duration_ms,
                      attributes_json=excluded.attributes_json;
                    """,
                    payload,
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def upsert_span(self, span: Dict[str, Any]) -> None:
        await self.init()
        db_path = self._config.db_path

        payload = (
            span.get("span_id"),
            span.get("trace_id"),
            span.get("parent_span_id"),
            span.get("name") or "",
            span.get("status"),
            float(span.get("start_time") or time.time()),
            span.get("end_time"),
            span.get("duration_ms"),
            _json_dumps(span.get("attributes") or {}),
            _json_dumps(span.get("events") or []),
        )

        def _sync():
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO spans(span_id, trace_id, parent_span_id, name, status, start_time, end_time, duration_ms, attributes_json, events_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(span_id) DO UPDATE SET
                      trace_id=excluded.trace_id,
                      parent_span_id=excluded.parent_span_id,
                      name=excluded.name,
                      status=excluded.status,
                      start_time=excluded.start_time,
                      end_time=excluded.end_time,
                      duration_ms=excluded.duration_ms,
                      attributes_json=excluded.attributes_json,
                      events_json=excluded.events_json;
                    """,
                    payload,
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def get_trace(self, trace_id: str, include_spans: bool = True) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM traces WHERE trace_id=?", (trace_id,)).fetchone()
                if not row:
                    return None
                trace = {
                    "trace_id": row["trace_id"],
                    "name": row["name"],
                    "status": row["status"],
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                    "duration_ms": row["duration_ms"],
                    "attributes": _json_loads(row["attributes_json"]) or {},
                }
                if include_spans:
                    spans = conn.execute(
                        "SELECT * FROM spans WHERE trace_id=? ORDER BY start_time ASC",
                        (trace_id,),
                    ).fetchall()
                    trace["spans"] = [
                        {
                            "span_id": s["span_id"],
                            "trace_id": s["trace_id"],
                            "parent_span_id": s["parent_span_id"],
                            "name": s["name"],
                            "status": s["status"],
                            "start_time": s["start_time"],
                            "end_time": s["end_time"],
                            "duration_ms": s["duration_ms"],
                            "attributes": _json_loads(s["attributes_json"]) or {},
                            "events": _json_loads(s["events_json"]) or [],
                        }
                        for s in spans
                    ]
                return trace
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_traces(self, limit: int = 100, offset: int = 0, status: Optional[str] = None) -> Tuple[List[Dict[str, Any]], int]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Tuple[List[Dict[str, Any]], int]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                if status:
                    total = conn.execute("SELECT COUNT(1) AS c FROM traces WHERE status=?", (status,)).fetchone()["c"]
                    rows = conn.execute(
                        "SELECT * FROM traces WHERE status=? ORDER BY start_time DESC LIMIT ? OFFSET ?",
                        (status, int(limit), int(offset)),
                    ).fetchall()
                else:
                    total = conn.execute("SELECT COUNT(1) AS c FROM traces").fetchone()["c"]
                    rows = conn.execute(
                        "SELECT * FROM traces ORDER BY start_time DESC LIMIT ? OFFSET ?",
                        (int(limit), int(offset)),
                    ).fetchall()
                items = [
                    {
                        "trace_id": r["trace_id"],
                        "name": r["name"],
                        "status": r["status"],
                        "start_time": r["start_time"],
                        "end_time": r["end_time"],
                        "duration_ms": r["duration_ms"],
                        "attributes": _json_loads(r["attributes_json"]) or {},
                    }
                    for r in rows
                ]
                return items, int(total)
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ==================== Graph restore/resume helpers ====================

    async def get_graph_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT checkpoint_id, run_id, step, state_json, created_at FROM graph_checkpoints WHERE checkpoint_id=?",
                    (checkpoint_id,),
                ).fetchone()
                if not row:
                    return None
                return {
                    "checkpoint_id": row["checkpoint_id"],
                    "run_id": row["run_id"],
                    "step": row["step"],
                    "state": _json_loads(row["state_json"]),
                    "created_at": row["created_at"],
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_graph_checkpoint_by_step(self, run_id: str, step: int) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    """
                    SELECT checkpoint_id, run_id, step, state_json, created_at
                    FROM graph_checkpoints
                    WHERE run_id=? AND step=?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (run_id, int(step)),
                ).fetchone()
                if not row:
                    return None
                return {
                    "checkpoint_id": row["checkpoint_id"],
                    "run_id": row["run_id"],
                    "step": row["step"],
                    "state": _json_loads(row["state_json"]),
                    "created_at": row["created_at"],
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_latest_graph_checkpoint(self, run_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    """
                    SELECT checkpoint_id, run_id, step, state_json, created_at
                    FROM graph_checkpoints
                    WHERE run_id=?
                    ORDER BY step DESC, created_at DESC
                    LIMIT 1
                    """,
                    (run_id,),
                ).fetchone()
                if not row:
                    return None
                return {
                    "checkpoint_id": row["checkpoint_id"],
                    "run_id": row["run_id"],
                    "step": row["step"],
                    "state": _json_loads(row["state_json"]),
                    "created_at": row["created_at"],
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def resume_graph_run(
        self,
        parent_run_id: str,
        checkpoint_id: str,
        new_run_id: Optional[str] = None,
        start_time: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        从 checkpoint 创建一个新的 graph_run（用于“可恢复执行”的语义），并返回新 run 的初始 state。
        注意：此方法仅提供“恢复状态+建档”；实际执行由上层组件决定。
        """
        await self.init()
        parent = await self.get_graph_run(parent_run_id)
        ckpt = await self.get_graph_checkpoint(checkpoint_id)
        if not parent or not ckpt:
            return None
        if ckpt["run_id"] != parent_run_id:
            return None

        # Idempotency: if already resumed from this checkpoint, return existing run
        db_path = self._config.db_path

        def _find_existing() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    """
                    SELECT run_id, graph_name, initial_state_json
                    FROM graph_runs
                    WHERE parent_run_id=? AND resumed_from_checkpoint_id=?
                    ORDER BY start_time DESC
                    LIMIT 1
                    """,
                    (parent_run_id, checkpoint_id),
                ).fetchone()
                if not row:
                    return None
                return {
                    "run_id": row["run_id"],
                    "graph_name": row["graph_name"],
                    "state": _json_loads(row["initial_state_json"]) or {},
                }
            finally:
                conn.close()

        existing = await anyio.to_thread.run_sync(_find_existing)
        if existing:
            return {
                "run_id": existing["run_id"],
                "graph_name": existing["graph_name"],
                "checkpoint_id": checkpoint_id,
                "state": existing["state"],
            }

        restored_state = ckpt.get("state") if isinstance(ckpt.get("state"), dict) else {}
        # Ensure restored state can be correlated to new run id (for callbacks / persistence)
        try:
            meta = restored_state.get("metadata") if isinstance(restored_state.get("metadata"), dict) else {}
            meta["graph_run_id"] = new_run_id or meta.get("graph_run_id")
            meta["parent_run_id"] = parent_run_id
            meta["resumed_from_checkpoint_id"] = checkpoint_id
            restored_state["metadata"] = meta
        except Exception:
            pass
        run_id = await self.start_graph_run(
            graph_name=parent["graph_name"],
            run_id=new_run_id,
            initial_state=restored_state,
            start_time=start_time,
            parent_run_id=parent_run_id,
            resumed_from_checkpoint_id=checkpoint_id,
        )
        # Update graph_run_id to the actual run_id if generated by store
        try:
            meta = restored_state.get("metadata") if isinstance(restored_state.get("metadata"), dict) else {}
            meta["graph_run_id"] = run_id
            restored_state["metadata"] = meta
        except Exception:
            pass
        return {"run_id": run_id, "graph_name": parent["graph_name"], "checkpoint_id": checkpoint_id, "state": restored_state}

    # ==================== execution <-> trace link queries ====================

    async def get_trace_id_by_execution_id(self, execution_id: str) -> Optional[str]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[str]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT trace_id FROM agent_executions WHERE id=?", (execution_id,)).fetchone()
                if row and row["trace_id"]:
                    return row["trace_id"]
                row = conn.execute("SELECT trace_id FROM skill_executions WHERE id=?", (execution_id,)).fetchone()
                if row and row["trace_id"]:
                    return row["trace_id"]
                return None
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_executions_by_trace_id(self, trace_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                agent_rows = conn.execute(
                    """
                    SELECT * FROM agent_executions
                    WHERE trace_id=?
                    ORDER BY start_time DESC
                    LIMIT ? OFFSET ?
                    """,
                    (trace_id, int(limit), int(offset)),
                ).fetchall()
                skill_rows = conn.execute(
                    """
                    SELECT * FROM skill_executions
                    WHERE trace_id=?
                    ORDER BY start_time DESC
                    LIMIT ? OFFSET ?
                    """,
                    (trace_id, int(limit), int(offset)),
                ).fetchall()

                agents = [
                    {
                        "execution_id": r["id"],
                        "agent_id": r["agent_id"],
                        "status": r["status"],
                        "start_time": r["start_time"],
                        "end_time": r["end_time"],
                        "duration_ms": r["duration_ms"],
                        "trace_id": r["trace_id"],
                    }
                    for r in agent_rows
                ]
                skills = [
                    {
                        "execution_id": r["id"],
                        "skill_id": r["skill_id"],
                        "status": r["status"],
                        "start_time": r["start_time"],
                        "end_time": r["end_time"],
                        "duration_ms": r["duration_ms"],
                        "trace_id": r["trace_id"],
                        "user_id": r["user_id"],
                    }
                    for r in skill_rows
                ]
                return {"agent_executions": agents, "skill_executions": skills}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ==================== Agent ====================

    async def upsert_agent_execution(self, record: Dict[str, Any]) -> None:
        await self.init()
        db_path = self._config.db_path

        payload = (
            record.get("id"),
            record.get("agent_id"),
            record.get("status"),
            _json_dumps(record.get("input")),
            _json_dumps(record.get("output")),
            record.get("error"),
            float(record.get("start_time") or 0.0),
            float(record.get("end_time") or 0.0),
            int(record.get("duration_ms") or 0),
            record.get("trace_id"),
            time.time(),
        )

        def _sync():
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO agent_executions
                      (id, agent_id, status, input_json, output_json, error, start_time, end_time, duration_ms, trace_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                      agent_id=excluded.agent_id,
                      status=excluded.status,
                      input_json=excluded.input_json,
                      output_json=excluded.output_json,
                      error=excluded.error,
                      start_time=excluded.start_time,
                      end_time=excluded.end_time,
                      duration_ms=excluded.duration_ms,
                      trace_id=excluded.trace_id;
                    """,
                    payload,
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def get_agent_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM agent_executions WHERE id = ?",
                    (execution_id,),
                ).fetchone()
                if not row:
                    return None
                return {
                    "id": row["id"],
                    "agent_id": row["agent_id"],
                    "status": row["status"],
                    "input": _json_loads(row["input_json"]),
                    "output": _json_loads(row["output_json"]),
                    "error": row["error"],
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                    "duration_ms": row["duration_ms"],
                    "trace_id": row["trace_id"] if "trace_id" in row.keys() else None,
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_agent_history(self, agent_id: str, limit: int, offset: int) -> Tuple[List[Dict[str, Any]], int]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Tuple[List[Dict[str, Any]], int]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                total = conn.execute(
                    "SELECT COUNT(1) AS c FROM agent_executions WHERE agent_id = ?",
                    (agent_id,),
                ).fetchone()["c"]
                rows = conn.execute(
                    """
                    SELECT * FROM agent_executions
                    WHERE agent_id = ?
                    ORDER BY start_time DESC
                    LIMIT ? OFFSET ?;
                    """,
                    (agent_id, int(limit), int(offset)),
                ).fetchall()
                items: List[Dict[str, Any]] = []
                for row in rows:
                    items.append(
                        {
                            "id": row["id"],
                            "agent_id": row["agent_id"],
                            "status": row["status"],
                            "input": _json_loads(row["input_json"]),
                            "output": _json_loads(row["output_json"]),
                            "error": row["error"],
                            "start_time": row["start_time"],
                            "end_time": row["end_time"],
                            "duration_ms": row["duration_ms"],
                            "trace_id": row["trace_id"] if "trace_id" in row.keys() else None,
                        }
                    )
                return items, int(total)
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ==================== Skill ====================

    async def upsert_skill_execution(self, record: Dict[str, Any]) -> None:
        await self.init()
        db_path = self._config.db_path

        payload = (
            record.get("id"),
            record.get("skill_id"),
            record.get("status"),
            _json_dumps(record.get("input")),
            _json_dumps(record.get("output")),
            record.get("error"),
            float(record.get("start_time") or 0.0),
            float(record.get("end_time") or 0.0),
            int(record.get("duration_ms") or 0),
            record.get("user_id"),
            record.get("trace_id"),
            time.time(),
        )

        def _sync():
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO skill_executions
                      (id, skill_id, status, input_json, output_json, error, start_time, end_time, duration_ms, user_id, trace_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                      skill_id=excluded.skill_id,
                      status=excluded.status,
                      input_json=excluded.input_json,
                      output_json=excluded.output_json,
                      error=excluded.error,
                      start_time=excluded.start_time,
                      end_time=excluded.end_time,
                      duration_ms=excluded.duration_ms,
                      user_id=excluded.user_id,
                      trace_id=excluded.trace_id;
                    """,
                    payload,
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def get_skill_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM skill_executions WHERE id = ?",
                    (execution_id,),
                ).fetchone()
                if not row:
                    return None
                return {
                    "id": row["id"],
                    "skill_id": row["skill_id"],
                    "status": row["status"],
                    "input": _json_loads(row["input_json"]),
                    "output": _json_loads(row["output_json"]),
                    "error": row["error"],
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                    "duration_ms": row["duration_ms"],
                    "user_id": row["user_id"],
                    "trace_id": row["trace_id"] if "trace_id" in row.keys() else None,
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_skill_executions(self, skill_id: str, limit: int, offset: int) -> Tuple[List[Dict[str, Any]], int]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Tuple[List[Dict[str, Any]], int]:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                total = conn.execute(
                    "SELECT COUNT(1) AS c FROM skill_executions WHERE skill_id = ?",
                    (skill_id,),
                ).fetchone()["c"]
                rows = conn.execute(
                    """
                    SELECT * FROM skill_executions
                    WHERE skill_id = ?
                    ORDER BY start_time DESC
                    LIMIT ? OFFSET ?;
                    """,
                    (skill_id, int(limit), int(offset)),
                ).fetchall()
                items: List[Dict[str, Any]] = []
                for row in rows:
                    items.append(
                        {
                            "id": row["id"],
                            "skill_id": row["skill_id"],
                            "status": row["status"],
                            "input": _json_loads(row["input_json"]),
                            "output": _json_loads(row["output_json"]),
                            "error": row["error"],
                            "start_time": row["start_time"],
                            "end_time": row["end_time"],
                            "duration_ms": row["duration_ms"],
                            "user_id": row["user_id"],
                            "trace_id": row["trace_id"] if "trace_id" in row.keys() else None,
                        }
                    )
                return items, int(total)
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)


_execution_store: Optional[ExecutionStore] = None


def get_execution_store(db_path: Optional[str] = None) -> ExecutionStore:
    """Process-wide singleton."""
    global _execution_store
    if _execution_store is None:
        db_path = db_path or os.environ.get("AIPLAT_EXECUTION_DB_PATH", "data/aiplat_executions.sqlite3")
        def _int_env(name: str) -> Optional[int]:
            v = os.environ.get(name)
            if v is None or str(v).strip() == "":
                return None
            try:
                return int(str(v).strip())
            except Exception:
                return None

        retention_days = _int_env("AIPLAT_EXECUTION_DB_RETENTION_DAYS")
        max_rows = _int_env("AIPLAT_EXECUTION_DB_MAX_ROWS_PER_ENTITY")
        prune_on_start = os.environ.get("AIPLAT_EXECUTION_DB_PRUNE_ON_START", "true").lower() not in ("0", "false", "no")
        vacuum_on_prune = os.environ.get("AIPLAT_EXECUTION_DB_VACUUM_ON_PRUNE", "false").lower() in ("1", "true", "yes")

        _execution_store = ExecutionStore(
            ExecutionStoreConfig(
                db_path=db_path,
                retention_days=retention_days,
                max_rows_per_entity=max_rows,
                prune_on_start=prune_on_start,
                vacuum_on_prune=vacuum_on_prune,
            )
        )
    return _execution_store
