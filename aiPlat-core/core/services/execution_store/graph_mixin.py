"""
Graph lifecycle Mixin — start, finish, checkpoint, list, get, resume.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
from ._base import _json_dumps, _json_loads


class GraphMixin:
    """Extracted from ExecutionStore."""
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
            conn = self._connect()
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
            conn = self._connect()
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
            conn = self._connect()
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
            conn = self._connect()
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
            conn = self._connect()
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
            conn = self._connect()
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

