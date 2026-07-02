"""
JobMixin — extracted from ExecutionStore events_mixin.py.

Auto-generated via Mixin split. Contains entity-specific CRUD methods.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
from ._base import _json_dumps, _json_loads


class JobMixin:
    """Extracted from ExecutionStore."""
    # ==================== Job Delivery Attempts / DLQ (Roadmap-3) ====================

    async def add_job_delivery_attempt(
        self,
        *,
        job_id: str,
        run_id: Optional[str],
        attempt: int,
        url: Optional[str],
        status: str,
        response_status: Optional[int] = None,
        error: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            rec = {
                "id": f"jda-{uuid.uuid4().hex[:12]}",
                "job_id": str(job_id),
                "run_id": str(run_id) if run_id else None,
                "attempt": int(attempt),
                "url": str(url) if url else None,
                "status": str(status),
                "response_status": int(response_status) if response_status is not None else None,
                "error": str(error) if error else None,
                "payload_json": _json_dumps(payload or {}),
                "created_at": now,
            }
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO job_delivery_attempts(
                      id, job_id, run_id, attempt, url, status, response_status, error, payload_json, created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?);
                    """,
                    (
                        rec["id"],
                        rec["job_id"],
                        rec["run_id"],
                        rec["attempt"],
                        rec["url"],
                        rec["status"],
                        rec["response_status"],
                        rec["error"],
                        rec["payload_json"],
                        rec["created_at"],
                    ),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {**row, "payload": _json_loads(row.get("payload_json")) or {}}

    async def list_job_delivery_attempts(
        self,
        *,
        job_id: Optional[str] = None,
        run_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                clauses = []
                params: List[Any] = []
                if job_id:
                    clauses.append("job_id=?")
                    params.append(str(job_id))
                if run_id:
                    clauses.append("run_id=?")
                    params.append(str(run_id))
                if status:
                    clauses.append("status=?")
                    params.append(str(status))
                where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
                total_row = conn.execute(
                    f"SELECT COUNT(1) AS c FROM job_delivery_attempts {where};", tuple(params)
                ).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT * FROM job_delivery_attempts {where} ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                    tuple(params + [int(limit), int(offset)]),
                ).fetchall()
                items = []
                for r in rows:
                    d = dict(r)
                    d["payload"] = _json_loads(d.get("payload_json")) or {}
                    items.append(d)
                return {"items": items, "total": total, "limit": int(limit), "offset": int(offset)}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def enqueue_job_delivery_dlq(
        self,
        *,
        job_id: str,
        run_id: Optional[str],
        url: Optional[str],
        delivery: Optional[Dict[str, Any]],
        payload: Optional[Dict[str, Any]],
        attempts: int,
        error: Optional[str],
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            rec = {
                "id": f"dlq-{uuid.uuid4().hex[:12]}",
                "job_id": str(job_id),
                "run_id": str(run_id) if run_id else None,
                "url": str(url) if url else None,
                "delivery_json": _json_dumps(delivery or {}),
                "payload_json": _json_dumps(payload or {}),
                "attempts": int(attempts),
                "error": str(error) if error else None,
                "status": "pending",
                "created_at": now,
                "resolved_at": None,
            }
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO job_delivery_dlq(
                      id, job_id, run_id, url, delivery_json, payload_json, attempts, error, status, created_at, resolved_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?);
                    """,
                    (
                        rec["id"],
                        rec["job_id"],
                        rec["run_id"],
                        rec["url"],
                        rec["delivery_json"],
                        rec["payload_json"],
                        rec["attempts"],
                        rec["error"],
                        rec["status"],
                        rec["created_at"],
                        rec["resolved_at"],
                    ),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {
            **row,
            "delivery": _json_loads(row.get("delivery_json")) or {},
            "payload": _json_loads(row.get("payload_json")) or {},
        }

    async def list_job_delivery_dlq(
        self,
        *,
        status: Optional[str] = None,
        job_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                clauses = []
                params: List[Any] = []
                if status:
                    clauses.append("status = ?")
                    params.append(str(status))
                if job_id:
                    clauses.append("job_id = ?")
                    params.append(str(job_id))
                where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM job_delivery_dlq {where};", params).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT * FROM job_delivery_dlq {where} ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                    [*params, int(limit), int(offset)],
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items = []
        for r in res.get("items") or []:
            items.append(
                {
                    **r,
                    "delivery": _json_loads(r.get("delivery_json")) or {},
                    "payload": _json_loads(r.get("payload_json")) or {},
                }
            )
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    async def get_job_delivery_dlq_item(self, dlq_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM job_delivery_dlq WHERE id = ?;", (str(dlq_id),)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        r = await anyio.to_thread.run_sync(_sync)
        if not r:
            return None
        return {**r, "delivery": _json_loads(r.get("delivery_json")) or {}, "payload": _json_loads(r.get("payload_json")) or {}}

    async def mark_job_delivery_dlq_resolved(self, dlq_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "UPDATE job_delivery_dlq SET status='resolved', resolved_at=? WHERE id=?;",
                    (time.time(), str(dlq_id)),
                )
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return bool(await anyio.to_thread.run_sync(_sync))

    async def delete_job_delivery_dlq_item(self, dlq_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM job_delivery_dlq WHERE id=?;", (str(dlq_id),))
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return bool(await anyio.to_thread.run_sync(_sync))

