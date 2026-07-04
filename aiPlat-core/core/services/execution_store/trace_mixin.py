"""
Trace Mixin — upsert/get/list traces/spans, execution-link queries.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
import anyio
from ._base import _json_dumps, _json_loads


class TraceMixin:
    """Extracted from ExecutionStore."""
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
            conn = self._connect()
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
            conn = self._connect()
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
            conn = self._connect()
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
            conn = self._connect()
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
            conn = self._connect()
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
            conn = self._connect()
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
            conn = self._connect()
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
            conn = self._connect()
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
        except Exception as e:
            logging.debug(str(e), exc_info=True)
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
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        return {"run_id": run_id, "graph_name": parent["graph_name"], "checkpoint_id": checkpoint_id, "state": restored_state}

    # ==================== execution <-> trace link queries ====================

    async def get_trace_id_by_execution_id(self, execution_id: str) -> Optional[str]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[str]:
            conn = self._connect()
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
            conn = self._connect()
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
                        "error": r["error"],
                        "error_code": r["error_code"] if "error_code" in r.keys() else None,
                        "metadata": _json_loads(r["metadata_json"]) if "metadata_json" in r.keys() else None,
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
                        "error": r["error"],
                        "error_code": r["error_code"] if "error_code" in r.keys() else None,
                        "metadata": _json_loads(r["metadata_json"]) if "metadata_json" in r.keys() else None,
                    }
                    for r in skill_rows
                ]
                return {"agent_executions": agents, "skill_executions": skills}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

