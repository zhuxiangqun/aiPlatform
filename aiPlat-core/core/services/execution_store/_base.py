"""
ExecutionStore (SQLite)

用于持久化 agent/skill 的执行记录与历史查询。

目标（P0 最小可用）：
- 替代 core/server.py 的全局内存 dict（_agent_executions/_agent_history/_skill_executions）
- 服务重启后仍可查询 execution_id 与 history

DEPRECATED: migrate to platform layer — tenant_quotas management should live in platform.
Per architecture contract (docs/index.md §Layer 2).

SPLIT PLAN (audit 2026-05):
  9007 lines — target: per-entity modules ≤ 1000 lines each.
  ─────────
  - execution_store_runs.py      (~2000 lines): run CRUD, status transitions, run summaries
  - execution_store_memory.py    (~1500 lines): agent memory tables, memory CRUD, FTS
  - execution_store_skills.py    (~1500 lines): skill execution log, evals, tests
  - execution_store_config.py    (~1500 lines): config_registry CRUD (tables, assets)
  - execution_store_jobs.py      (~1500 lines): job queue, scheduler, dispatcher
  - execution_store.py            (~ 500 lines): base class, connection pool, migration bootstrap
  ─────────
  Status: planned, not started. Tracked in core/services/BOUNDARY.yaml.
"""

from __future__ import annotations
import logging

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import json
import os
import sqlite3
import time
import uuid
import anyio

from ..execution_store_schema import ALL_TABLES


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def _json_loads(s: Optional[str]) -> Any:
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return s


# ==================== Change Control derived state ====================


def _derive_change_summary(latest: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Derive a stable "state machine" summary from the latest changeset event.
    This is UI-facing and should be conservative.
    """
    if not isinstance(latest, dict) or not latest:
        return {
            "derived_state": "unknown",
            "latest_status": None,
            "latest_name": None,
            "latest_created_at": None,
            "latest_run_id": None,
            "latest_trace_id": None,
            "approval_request_id": None,
        }

    status = str(latest.get("status") or "").lower() or None
    name = str(latest.get("name") or "") or None
    approval_request_id = latest.get("approval_request_id")
    run_id = latest.get("run_id")
    trace_id = latest.get("trace_id")
    created_at = latest.get("created_at")

    derived = "unknown"
    # normalize more domain statuses
    if status in {"blocked", "deny", "denied"}:
        derived = "blocked"
    elif status in {"approval_required", "waiting_approval", "pending"}:
        derived = "approval_required"
    elif status in {"failed", "error"}:
        derived = "failed"
    elif status in {"success", "completed", "ok", "published", "rolled_back", "no_op"}:
        derived = "success"

    # name-based hints (best-effort)
    if name and str(name).startswith(("config_publish_pending", "config_rollback_pending")):
        derived = "approval_required"

    if approval_request_id and derived not in {"blocked", "failed"}:
        if derived != "success":
            derived = "approval_required"

    return {
        "derived_state": derived,
        "latest_status": status,
        "latest_name": name,
        "latest_created_at": created_at,
        "latest_run_id": run_id,
        "latest_trace_id": trace_id,
        "approval_request_id": str(approval_request_id) if approval_request_id else None,
    }


@dataclass(frozen=True)
class ExecutionStoreConfig:
    db_path: str
    retention_days: Optional[int] = None
    max_rows_per_entity: Optional[int] = None
    prune_on_start: bool = True
    vacuum_on_prune: bool = False


class _ExecutionStoreBase:
    CURRENT_SCHEMA_VERSION = 51

    def __init__(self, config: ExecutionStoreConfig):
        self._config = config
        self._init_once_lock = anyio.Lock()
        self._inited = False

    def _connect(self) -> sqlite3.Connection:
        """Create a properly configured SQLite connection.
        
        Centralized connection factory — all methods use this instead of raw
        sqlite3.connect(). Ensures consistent WAL mode, timeout, and pragma settings.
        """
        conn = sqlite3.connect(self._config.db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.row_factory = sqlite3.Row
        return conn

    async def init(self) -> None:
        """Init database and run schema migrations (idempotent)."""
        async with self._init_once_lock:
            if self._inited:
                return

            db_path = self._config.db_path
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

            def _init_sync():
                conn = self._connect()
                try:
                    from ..execution_store_schema import execute_schema
                    execute_schema(conn)
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
                    try:
                        conn.execute(
                            """
                            DELETE FROM syscall_events
                            WHERE id IN (
                              SELECT id FROM syscall_events
                    ORDER BY created_at ASC
                              LIMIT -1 OFFSET ?
                            );
                            """,
                            (int(max_rows),),  # noqa: F821
                        )
                    except Exception as e:
                        logging.debug(str(e), exc_info=True)
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
                    from .schema import run_migrations
                    current = run_migrations(conn, current, self.CURRENT_SCHEMA_VERSION)

                    conn.commit()
                finally:
                    conn.close()

            await anyio.to_thread.run_sync(_init_sync)
            self._inited = True

            # Optional retention pruning on start (best effort)
            if self._config.prune_on_start and (self._config.retention_days or self._config.max_rows_per_entity):
                try:
                    await self.prune()
                except Exception as e:
                    logging.debug(str(e), exc_info=True)

    async def get_schema_version(self) -> int:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> int:
            conn = self._connect()
            try:
                row = conn.execute("SELECT v FROM aiplat_meta WHERE k='schema_version'").fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_syscall_event_stats(
        self,
        *,
        window_hours: int = 24,
        top_n: int = 10,
        kind: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Roadmap-0/2/3 observability: basic aggregated syscall stats (best-effort).
        """
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                now = time.time()
                since = now - float(max(int(window_hours), 1)) * 3600.0
                where = "WHERE created_at >= ?"
                params: List[Any] = [since]
                if kind:
                    where += " AND kind = ?"
                    params.append(str(kind))

                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM syscall_events {where};", params).fetchone()
                total = int(total_row["c"] if total_row else 0)

                by_kind = {
                    r["kind"]: int(r["c"])
                    for r in conn.execute(
                        f"SELECT kind, COUNT(1) AS c FROM syscall_events {where} GROUP BY kind;", params
                    ).fetchall()
                }
                by_status = {
                    r["status"]: int(r["c"])
                    for r in conn.execute(
                        f"SELECT status, COUNT(1) AS c FROM syscall_events {where} GROUP BY status;", params
                    ).fetchall()
                }

                top_names = [
                    dict(r)
                    for r in conn.execute(
                        f"""
                        SELECT kind, name, COUNT(1) AS count, AVG(duration_ms) AS avg_ms
                        FROM syscall_events
                        {where}
                        GROUP BY kind, name
                        ORDER BY count DESC
                        LIMIT ?;
                        """,
                        [*params, int(top_n)],
                    ).fetchall()
                ]
                top_failed = [
                    dict(r)
                    for r in conn.execute(
                        f"""
                        SELECT kind, name, COUNT(1) AS count
                        FROM syscall_events
                        {where} AND status = 'failed'
                        GROUP BY kind, name
                        ORDER BY count DESC
                        LIMIT ?;
                        """,
                        [*params, int(top_n)],
                    ).fetchall()
                ]

                top_error_codes = [
                    dict(r)
                    for r in conn.execute(
                        f"""
                        SELECT error_code, COUNT(1) AS count
                        FROM syscall_events
                        {where} AND error_code IS NOT NULL AND error_code != ''
                        GROUP BY error_code
                        ORDER BY count DESC
                        LIMIT ?;
                        """,
                        [*params, int(top_n)],
                    ).fetchall()
                ]
                top_failed_error_codes = [
                    dict(r)
                    for r in conn.execute(
                        f"""
                        SELECT error_code, COUNT(1) AS count
                        FROM syscall_events
                        {where} AND status = 'failed' AND error_code IS NOT NULL AND error_code != ''
                        GROUP BY error_code
                        ORDER BY count DESC
                        LIMIT ?;
                        """,
                        [*params, int(top_n)],
                    ).fetchall()
                ]

                # Last N hours failure trend (hourly buckets).
                trend = [
                    dict(r)
                    for r in conn.execute(
                        f"""
                        SELECT
                          strftime('%Y-%m-%d %H:00:00', datetime(created_at, 'unixepoch')) AS bucket,
                          COUNT(1) AS failed
                        FROM syscall_events
                        {where} AND status = 'failed'
                        GROUP BY bucket
                        ORDER BY bucket ASC;
                        """,
                        params,
                    ).fetchall()
                ]

                return {
                    "window_hours": int(window_hours),
                    "since": since,
                    "total": total,
                    "by_kind": by_kind,
                    "by_status": by_status,
                    "top_names": top_names,
                    "top_failed": top_failed,
                    "top_error_codes": top_error_codes,
                    "top_failed_error_codes": top_failed_error_codes,
                    "failed_trend_hourly": trend,
                }
            finally:
                conn.close()
        return await anyio.to_thread.run_sync(_sync)


    async def get_recent_syscall_events(
        self, run_id: str = "", limit: int = 50
    ) -> List[Dict[str, Any]]:
        """返回指定 pipeline run 的最近 N 条 syscall 事件。

        用于 v5.0 运行时剖面校准——对比 Agent 声明 vs 实际行为。
        run_id 为空时返回全局最近事件。
        """
        await self.init()
        db_path = self._config.db_path

        def _sync() -> List[Dict[str, Any]]:
            conn = sqlite3.connect(db_path, timeout=5.0)
            try:
                if run_id:
                    rows = conn.execute(
                        """SELECT kind, name, status, created_at
                           FROM syscall_events WHERE run_id = ?
                           ORDER BY created_at DESC LIMIT ?""",
                        (run_id, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """SELECT kind, name, status, created_at
                           FROM syscall_events
                           ORDER BY created_at DESC LIMIT ?""",
                        (limit,),
                    ).fetchall()
                return [{
                    "kind": r[0] or "",
                    "name": r[1] or "",
                    "status": r[2] or "",
                    "created_at": r[3] or "",
                } for r in rows]
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
            conn = self._connect()
            try:
                conn.execute("PRAGMA foreign_keys=ON;")
                deleted = {"agent_executions": 0, "skill_executions": 0, "graph_runs": 0, "graph_checkpoints": 0, "traces": 0, "spans": 0, "syscall_events": 0}

                if retention_days is not None:
                    cur = conn.execute("DELETE FROM agent_executions WHERE created_at < ?", (cutoff,))
                    deleted["agent_executions"] += cur.rowcount or 0
                    cur = conn.execute("DELETE FROM skill_executions WHERE created_at < ?", (cutoff,))
                    deleted["skill_executions"] += cur.rowcount or 0
                    cur = conn.execute("DELETE FROM graph_runs WHERE start_time < ?", (cutoff,))
                    deleted["graph_runs"] += cur.rowcount or 0
                    try:
                        cur = conn.execute("DELETE FROM syscall_events WHERE created_at < ?", (cutoff,))
                        deleted["syscall_events"] += cur.rowcount or 0
                    except Exception as e:
                        logging.debug(str(e), exc_info=True)
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


