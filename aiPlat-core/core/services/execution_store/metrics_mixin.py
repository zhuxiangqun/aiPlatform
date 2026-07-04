"""
MetricsMixin — extracted from ExecutionStore runs_mixin.py.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
import anyio
from ._base import _json_dumps, _json_loads


class MetricsMixin:
    """Extracted from ExecutionStore."""
    async def exec_backend_metrics_summary(self, *, window_hours: int = 24, limit: int = 20) -> Dict[str, Any]:
        """
        Aggregate per-exec-backend metrics using run_events within a time window.
        Metrics:
          - total_runs
          - done_runs
          - ok_runs
          - failed_runs
          - policy_denied_count (best-effort: any *_end event with payload.status == policy_denied)
          - avg_latency_ms (run_end.created_at - run_start.created_at)
        """
        await self.init()
        import time

        now = time.time()
        since = now - max(1, int(window_hours)) * 3600
        db_path = self._config.db_path

        def _sync() -> List[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    """
                    SELECT run_id, type, payload_json, created_at
                    FROM run_events
                    WHERE created_at >= ?
                      AND type IN ('run_start','run_end','tool_end','skill_end','agent_end','graph_end')
                    ORDER BY created_at ASC
                    """,
                    (float(since),),
                ).fetchall()
                out: List[Dict[str, Any]] = []
                for r in rows:
                    out.append(
                        {
                            "run_id": r["run_id"],
                            "type": r["type"],
                            "payload": _json_loads(r["payload_json"]) or {},
                            "created_at": float(r["created_at"] or 0.0),
                        }
                    )
                return out
            finally:
                conn.close()

        items = await anyio.to_thread.run_sync(_sync)

        # Build run map
        runs: Dict[str, Dict[str, Any]] = {}
        for ev in items:
            rid = str(ev.get("run_id") or "")
            if not rid:
                continue
            r = runs.setdefault(rid, {"run_id": rid})
            typ = str(ev.get("type") or "")
            payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
            t = float(ev.get("created_at") or 0.0)
            if typ == "run_start":
                r["start_at"] = t
                r["exec_backend"] = payload.get("exec_backend") or r.get("exec_backend") or "unknown"
            elif typ == "run_end":
                r["end_at"] = t
                r["end_status"] = payload.get("status") or r.get("end_status")
            # policy denied signal: any *_end status=policy_denied
            if typ.endswith("_end"):
                st = payload.get("status")
                if isinstance(st, str) and st.lower() == "policy_denied":
                    r["policy_denied"] = True

        # Aggregate by backend
        agg: Dict[str, Dict[str, Any]] = {}

        def _is_ok_status(st: Any) -> bool:
            s = str(st or "").lower()
            return s in ("completed", "success", "succeeded", "ok")

        for r in runs.values():
            backend = str(r.get("exec_backend") or "unknown")
            a = agg.setdefault(
                backend,
                {
                    "exec_backend": backend,
                    "total_runs": 0,
                    "done_runs": 0,
                    "ok_runs": 0,
                    "failed_runs": 0,
                    "policy_denied_count": 0,
                    "avg_latency_ms": None,
                    "_lat_sum": 0.0,
                    "_lat_n": 0,
                },
            )
            a["total_runs"] += 1
            if r.get("policy_denied"):
                a["policy_denied_count"] += 1
            if r.get("end_at") and r.get("start_at"):
                a["done_runs"] += 1
                if _is_ok_status(r.get("end_status")):
                    a["ok_runs"] += 1
                else:
                    a["failed_runs"] += 1
                lat_ms = (float(r["end_at"]) - float(r["start_at"])) * 1000.0
                if lat_ms >= 0:
                    a["_lat_sum"] += lat_ms
                    a["_lat_n"] += 1

        out = list(agg.values())
        for a in out:
            n = int(a.pop("_lat_n", 0) or 0)
            s = float(a.pop("_lat_sum", 0.0) or 0.0)
            a["avg_latency_ms"] = round(s / n, 2) if n > 0 else None
            # derived rates (best-effort)
            total = int(a.get("total_runs") or 0)
            ok = int(a.get("ok_runs") or 0)
            a["success_rate"] = round(ok / total, 4) if total > 0 else None

        out.sort(key=lambda x: int(x.get("total_runs") or 0), reverse=True)
        out = out[: max(1, int(limit))]
        return {"window_hours": int(window_hours), "since": since, "until": now, "items": out}

    # ---------------------------------------------------------------------
    # PR-04: Session lane (per-session serialization) - locks + queue
    # ---------------------------------------------------------------------

    async def try_acquire_session_lock(
        self,
        *,
        tenant_id: Optional[str],
        session_id: str,
        run_id: str,
        ttl_seconds: int = 300,
    ) -> bool:
        """
        Best-effort lock to ensure only one active run per (tenant, session).
        Returns True if acquired (or renewed), False if held by another run.
        """
        await self.init()
        db_path = self._config.db_path
        t = str(tenant_id or "")

        def _sync() -> bool:
            now = float(time.time())
            exp = now + float(max(int(ttl_seconds), 1))
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT run_id, expires_at FROM session_locks WHERE tenant_id=? AND session_id=?",
                    (t, str(session_id)),
                ).fetchone()
                if row:
                    cur_run = row["run_id"]
                    cur_exp = float(row["expires_at"] or 0.0)
                    if cur_run != str(run_id) and cur_exp > now:
                        return False
                # Upsert lock
                conn.execute(
                    """
                    INSERT INTO session_locks(tenant_id, session_id, run_id, acquired_at, expires_at)
                    VALUES(?, ?, ?, ?, ?)
                    ON CONFLICT(tenant_id, session_id) DO UPDATE SET
                      run_id=excluded.run_id,
                      acquired_at=excluded.acquired_at,
                      expires_at=excluded.expires_at
                    """,
                    (t, str(session_id), str(run_id), now, exp),
                )
                conn.commit()
                return True
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def release_session_lock(self, *, tenant_id: Optional[str], session_id: str, run_id: str) -> None:
        await self.init()
        db_path = self._config.db_path
        t = str(tenant_id or "")

        def _sync() -> None:
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM session_locks WHERE tenant_id=? AND session_id=? AND run_id=?",
                    (t, str(session_id), str(run_id)),
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def enqueue_session_run(
        self,
        *,
        tenant_id: Optional[str],
        session_id: str,
        run_id: str,
        kind: str,
        target_id: str,
        user_id: Optional[str],
        payload: Optional[Dict[str, Any]],
        queue_mode: Optional[str] = None,
    ) -> None:
        await self.init()
        db_path = self._config.db_path
        t = str(tenant_id or "")

        def _sync() -> None:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO session_queue(tenant_id, session_id, run_id, kind, target_id, user_id, queue_mode, status, payload_json, created_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO NOTHING;
                    """,
                    (
                        t,
                        str(session_id),
                        str(run_id),
                        str(kind),
                        str(target_id),
                        str(user_id) if user_id else None,
                        str(queue_mode) if queue_mode else None,
                        "queued",
                        _json_dumps(payload or {}),
                        float(time.time()),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def dequeue_session_run(self, *, tenant_id: Optional[str], session_id: str) -> Optional[Dict[str, Any]]:
        """Pop the oldest queued item for session; mark it as dequeued."""
        await self.init()
        db_path = self._config.db_path
        t = str(tenant_id or "")

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    """
                    SELECT id, run_id, kind, target_id, user_id, queue_mode, payload_json, created_at
                    FROM session_queue
                    WHERE tenant_id=? AND session_id=? AND status='queued'
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    (t, str(session_id)),
                ).fetchone()
                if not row:
                    return None
                conn.execute("UPDATE session_queue SET status='dequeued' WHERE id=?", (int(row["id"]),))
                conn.commit()
                return {
                    "id": int(row["id"]),
                    "tenant_id": t,
                    "session_id": str(session_id),
                    "run_id": row["run_id"],
                    "kind": row["kind"],
                    "target_id": row["target_id"],
                    "user_id": row["user_id"],
                    "queue_mode": row["queue_mode"],
                    "payload": _json_loads(row["payload_json"]) or {},
                    "created_at": float(row["created_at"] or 0.0),
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_run_summary(self, *, run_id: str) -> Optional[Dict[str, Any]]:
        """
        Best-effort unified run view across agent/skill/tool executions.
        Assumption: execution_id == run_id (post v2).
        """
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                # agent
                row = conn.execute("SELECT * FROM agent_executions WHERE id=? LIMIT 1", (run_id,)).fetchone()
                if row:
                    meta = _json_loads(row["metadata_json"]) if "metadata_json" in row.keys() else {}
                    meta = meta or {}
                    err_obj = meta.get("error_detail") if isinstance(meta.get("error_detail"), dict) else None
                    return {
                        "run_id": row["id"],
                        "kind": "agent",
                        "target_type": "agent",
                        "target_id": row["agent_id"],
                        "trace_id": row["trace_id"],
                        "tenant_id": row["tenant_id"] if "tenant_id" in row.keys() else None,
                        "status": row["status"],
                        "start_time": row["start_time"],
                        "end_time": row["end_time"],
                        "error_code": row["error_code"],
                        "error_message": row["error"] if "error" in row.keys() else None,
                        "error": err_obj or None,
                        "output": _json_loads(row["output_json"]) if "output_json" in row.keys() else None,
                        "user_id": meta.get("user_id"),
                        "session_id": meta.get("session_id") or (meta.get("context") or {}).get("session_id") if isinstance(meta.get("context"), dict) else None,
                    }
                # skill
                row = conn.execute("SELECT * FROM skill_executions WHERE id=? LIMIT 1", (run_id,)).fetchone()
                if row:
                    meta = _json_loads(row["metadata_json"]) if "metadata_json" in row.keys() else {}
                    meta = meta or {}
                    err_obj = meta.get("error_detail") if isinstance(meta.get("error_detail"), dict) else None
                    return {
                        "run_id": row["id"],
                        "kind": "skill",
                        "target_type": "skill",
                        "target_id": row["skill_id"],
                        "trace_id": row["trace_id"],
                        "tenant_id": row["tenant_id"] if "tenant_id" in row.keys() else None,
                        "status": row["status"],
                        "start_time": row["start_time"],
                        "end_time": row["end_time"],
                        "error_code": row["error_code"],
                        "error_message": row["error"] if "error" in row.keys() else None,
                        "error": err_obj or None,
                        "output": _json_loads(row["output_json"]) if "output_json" in row.keys() else None,
                        "user_id": row["user_id"] if "user_id" in row.keys() else meta.get("user_id"),
                        "session_id": meta.get("session_id") or (meta.get("context") or {}).get("session_id") if isinstance(meta.get("context"), dict) else None,
                    }
                # tool
                # NOTE: tool_executions is not a guaranteed table in all schema versions.
                # Prefer reconstructing a best-effort summary from run_events.
                try:
                    row = conn.execute("SELECT * FROM tool_executions WHERE id=? LIMIT 1", (run_id,)).fetchone()
                    if row:
                        meta = _json_loads(row["metadata_json"]) if "metadata_json" in row.keys() else {}
                        meta = meta or {}
                        err_obj = meta.get("error_detail") if isinstance(meta.get("error_detail"), dict) else None
                        return {
                            "run_id": row["id"],
                            "kind": "tool",
                            "target_type": "tool",
                            "target_id": row["tool_name"],
                            "trace_id": row["trace_id"],
                            "tenant_id": row["tenant_id"] if "tenant_id" in row.keys() else None,
                            "status": row["status"],
                            "start_time": row["start_time"],
                            "end_time": row["end_time"],
                            "error_code": row["error_code"],
                            "error_message": row["error"] if "error" in row.keys() else None,
                            "error": err_obj or None,
                            "output": _json_loads(row["output_json"]) if "output_json" in row.keys() else None,
                            "user_id": row["user_id"] if "user_id" in row.keys() else meta.get("user_id"),
                            "session_id": row["session_id"] if "session_id" in row.keys() else (meta.get("context") or {}).get("session_id") if isinstance(meta.get("context"), dict) else None,
                        }
                except Exception as e:
                    logging.debug(str(e), exc_info=True)

                # Fallback: build run summary from run_events (run_start/run_end).
                try:
                    start = conn.execute(
                        "SELECT seq, trace_id, tenant_id, payload_json, created_at FROM run_events WHERE run_id=? AND type='run_start' ORDER BY seq ASC LIMIT 1",
                        (run_id,),
                    ).fetchone()
                    if start:
                        start_payload = _json_loads(start["payload_json"]) or {}
                        kind = str(start_payload.get("kind") or "unknown")
                        trace_id = start["trace_id"]
                        tenant_id = start["tenant_id"]
                        start_time = start["created_at"]
                        end = conn.execute(
                            "SELECT seq, payload_json, created_at FROM run_events WHERE run_id=? AND type='run_end' ORDER BY seq DESC LIMIT 1",
                            (run_id,),
                        ).fetchone()
                        end_payload = _json_loads(end["payload_json"]) or {} if end else {}
                        status = (
                            str(end_payload.get("status") or "running")
                            if end
                            else str(start_payload.get("status") or "running")
                        )
                        end_time = end["created_at"] if end else None
                        target_id = (
                            start_payload.get("agent_id")
                            or start_payload.get("skill_id")
                            or start_payload.get("tool_name")
                            or end_payload.get("tool_name")
                            or end_payload.get("agent_id")
                            or end_payload.get("skill_id")
                        )
                        session_id = (
                            start_payload.get("session_id")
                            or (start_payload.get("context") or {}).get("session_id")
                            if isinstance(start_payload.get("context"), dict)
                            else None
                        )
                        user_id = start_payload.get("user_id")
                        return {
                            "run_id": run_id,
                            "kind": kind,
                            "target_type": kind,
                            "target_id": target_id,
                            "trace_id": trace_id,
                            "status": status,
                            "start_time": start_time,
                            "end_time": end_time,
                            "error_code": None,
                            "error_message": end_payload.get("error"),
                            "error": None,
                            "user_id": user_id,
                            "session_id": session_id,
                            "tenant_id": tenant_id,
                        }
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
                return None
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

