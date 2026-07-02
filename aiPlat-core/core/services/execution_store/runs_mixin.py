"""
RunsMixin — extracted from ExecutionStore.

Auto-generated via Mixin split from events_mixin.py.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
from ._base import _json_dumps, _json_loads


class RunsMixin:
    """Extracted from ExecutionStore."""
    # ==================== Runs / Run events (platform contract) ====================

    async def get_run_id_for_request(self, *, request_id: str, tenant_id: Optional[str] = None) -> Optional[str]:
        """Return existing run_id for a (tenant_id, request_id) pair."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[str]:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT run_id FROM request_dedup WHERE request_id=? AND (tenant_id=? OR tenant_id IS NULL OR ? IS NULL) LIMIT 1",
                    (request_id, tenant_id, tenant_id),
                ).fetchone()
                return str(row[0]) if row and row[0] else None
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def remember_request_run_id(self, *, request_id: str, run_id: str, tenant_id: Optional[str] = None) -> None:
        """Insert request_id -> run_id mapping (best-effort, idempotent)."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> None:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO request_dedup(tenant_id, request_id, run_id, created_at)
                    VALUES(?, ?, ?, ?)
                    ON CONFLICT(tenant_id, request_id) DO NOTHING;
                    """,
                    (tenant_id, request_id, run_id, float(time.time())),
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def append_run_event(
        self,
        *,
        run_id: str,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> int:
        """Append an event and return its seq."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> int:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT COALESCE(MAX(seq), 0) AS m FROM run_events WHERE run_id=?", (run_id,)).fetchone()
                next_seq = int(row["m"] if row else 0) + 1
                conn.execute(
                    """
                    INSERT INTO run_events(run_id, seq, tenant_id, trace_id, type, payload_json, created_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        run_id,
                        next_seq,
                        tenant_id,
                        trace_id,
                        str(event_type),
                        _json_dumps(payload or {}),
                        float(time.time()),
                    ),
                )
                conn.commit()
                return next_seq
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_run_events(
        self,
        *,
        run_id: str,
        after_seq: int = 0,
        limit: int = 200,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    """
                    SELECT seq, type, payload_json, trace_id, tenant_id, created_at
                    FROM run_events
                    WHERE run_id=? AND seq > ?
                    ORDER BY seq ASC
                    LIMIT ?;
                    """,
                    (run_id, int(after_seq), int(limit)),
                ).fetchall()
                items = []
                last_seq = int(after_seq)
                for r in rows:
                    last_seq = int(r["seq"])
                    items.append(
                        {
                            "seq": int(r["seq"]),
                            "type": r["type"],
                            "payload": _json_loads(r["payload_json"]) or {},
                            "trace_id": r["trace_id"],
                            "tenant_id": r["tenant_id"],
                            "created_at": r["created_at"],
                        }
                    )
                return {"items": items, "after_seq": int(after_seq), "last_seq": last_seq}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_run_start_event(self, *, run_id: str) -> Optional[Dict[str, Any]]:
        """Return the first run_start event payload (best-effort)."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT seq, trace_id, tenant_id, payload_json, created_at FROM run_events WHERE run_id=? AND type='run_start' ORDER BY seq ASC LIMIT 1",
                    (str(run_id),),
                ).fetchone()
                if not row:
                    return None
                return {
                    "seq": int(row["seq"]),
                    "trace_id": row["trace_id"],
                    "tenant_id": row["tenant_id"],
                    "payload": _json_loads(row["payload_json"]) or {},
                    "created_at": float(row["created_at"] or 0.0),
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def has_run_end(self, *, run_id: str) -> bool:
        """Check if run has any run_end event."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT 1 FROM run_events WHERE run_id=? AND type='run_end' LIMIT 1",
                    (str(run_id),),
                ).fetchone()
                return bool(row)
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def is_cancel_requested(self, *, run_id: str) -> bool:
        """Check if run has a cancel_requested marker."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT 1 FROM run_events WHERE run_id=? AND type='cancel_requested' LIMIT 1",
                    (str(run_id),),
                ).fetchone()
                return bool(row)
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_session_queue_item(self, *, run_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a session_queue row by run_id (queued/dequeued/cancelled)."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    """
                    SELECT tenant_id, session_id, run_id, kind, target_id, user_id, queue_mode, status, payload_json, created_at
                    FROM session_queue
                    WHERE run_id=?
                    LIMIT 1
                    """,
                    (str(run_id),),
                ).fetchone()
                if not row:
                    return None
                return {
                    "tenant_id": row["tenant_id"],
                    "session_id": row["session_id"],
                    "run_id": row["run_id"],
                    "kind": row["kind"],
                    "target_id": row["target_id"],
                    "user_id": row["user_id"],
                    "queue_mode": row["queue_mode"],
                    "status": row["status"],
                    "payload": _json_loads(row["payload_json"]) or {},
                    "created_at": float(row["created_at"] or 0.0),
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def cancel_queued_run(self, *, run_id: str) -> bool:
        """Mark a queued session_queue item as cancelled (best-effort)."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "UPDATE session_queue SET status='cancelled' WHERE run_id=? AND status='queued'",
                    (str(run_id),),
                )
                conn.commit()
                return (cur.rowcount or 0) > 0
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    """Run requests + events + state checks."""
    pass
