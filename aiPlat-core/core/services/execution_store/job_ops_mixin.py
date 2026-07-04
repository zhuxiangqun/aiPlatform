"""
JobOpsMixin — extracted from ExecutionStore skill_mixin.py.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
import anyio
import uuid
from ._base import _json_dumps, _json_loads


class JobOpsMixin:
    """Extracted from ExecutionStore."""
    async def create_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            payload = {
                "id": job.get("id") or f"job-{uuid.uuid4().hex[:12]}",
                "name": str(job.get("name") or ""),
                "enabled": 1 if bool(job.get("enabled", True)) else 0,
                "cron": str(job.get("cron") or "* * * * *"),
                "timezone": job.get("timezone"),
                "kind": str(job.get("kind") or "agent"),
                "target_id": str(job.get("target_id") or ""),
                "user_id": job.get("user_id"),
                "session_id": job.get("session_id"),
                "payload_json": _json_dumps(job.get("payload") or {}),
                "options_json": _json_dumps(job.get("options") or {}),
                "delivery_json": _json_dumps(job.get("delivery") or {}),
                "last_run_at": job.get("last_run_at"),
                "next_run_at": job.get("next_run_at"),
                "created_at": job.get("created_at") or now,
                "updated_at": job.get("updated_at") or now,
            }
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO jobs(
                      id,name,enabled,cron,timezone,kind,target_id,user_id,session_id,
                      payload_json,options_json,delivery_json,last_run_at,next_run_at,created_at,updated_at
                    ) VALUES(
                      :id,:name,:enabled,:cron,:timezone,:kind,:target_id,:user_id,:session_id,
                      :payload_json,:options_json,:delivery_json,:last_run_at,:next_run_at,:created_at,:updated_at
                    );
                    """,
                    payload,
                )
                conn.commit()
                return payload
            finally:
                conn.close()

        rec = await anyio.to_thread.run_sync(_sync)
        return self._job_row_to_obj(rec)

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
                if not row:
                    return None
                return dict(row)
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return self._job_row_to_obj(row) if row else None

    async def list_jobs(self, *, limit: int = 100, offset: int = 0, enabled: Optional[bool] = None) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                where = ""
                args: List[Any] = []
                if enabled is not None:
                    where = "WHERE enabled = ?"
                    args.append(1 if enabled else 0)

                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM jobs {where};", args).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"""
                    SELECT * FROM jobs
                    {where}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?;
                    """,
                    [*args, int(limit), int(offset)],
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        return {
            "items": [self._job_row_to_obj(r) for r in (res.get("items") or [])],
            "total": int(res.get("total") or 0),
            "limit": int(limit),
            "offset": int(offset),
        }

    async def update_job(self, job_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
                if not row:
                    return None
                cur = dict(row)
                now = time.time()
                updated = dict(cur)
                for k in ("name", "cron", "timezone", "kind", "target_id", "user_id", "session_id", "last_run_at", "next_run_at"):
                    if k in patch:
                        updated[k] = patch.get(k)
                if "enabled" in patch:
                    updated["enabled"] = 1 if bool(patch.get("enabled")) else 0
                if "payload" in patch:
                    updated["payload_json"] = _json_dumps(patch.get("payload") or {})
                if "options" in patch:
                    updated["options_json"] = _json_dumps(patch.get("options") or {})
                if "delivery" in patch:
                    updated["delivery_json"] = _json_dumps(patch.get("delivery") or {})
                updated["updated_at"] = now

                conn.execute(
                    """
                    UPDATE jobs SET
                      name=:name,
                      enabled=:enabled,
                      cron=:cron,
                      timezone=:timezone,
                      kind=:kind,
                      target_id=:target_id,
                      user_id=:user_id,
                      session_id=:session_id,
                      payload_json=:payload_json,
                      options_json=:options_json,
                      delivery_json=:delivery_json,
                      last_run_at=:last_run_at,
                      next_run_at=:next_run_at,
                      updated_at=:updated_at
                    WHERE id=:id;
                    """,
                    {**updated, "id": job_id},
                )
                conn.commit()
                row2 = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
                return dict(row2) if row2 else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return self._job_row_to_obj(row) if row else None

    async def delete_job(self, job_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM jobs WHERE id = ?;", (job_id,))
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_due_jobs(self, *, now_ts: float, limit: int = 20) -> List[Dict[str, Any]]:
        """List enabled jobs whose next_run_at <= now_ts."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> List[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM jobs
                    WHERE enabled = 1
                      AND next_run_at IS NOT NULL
                      AND next_run_at <= ?
                      AND (lock_until IS NULL OR lock_until <= ?)
                    ORDER BY next_run_at ASC
                    LIMIT ?;
                    """,
                    (float(now_ts), float(now_ts), int(limit)),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

        rows = await anyio.to_thread.run_sync(_sync)
        return [self._job_row_to_obj(r) for r in rows]

    async def acquire_job_lock(self, job_id: str, *, owner: str, ttl_seconds: float = 300.0) -> bool:
        """
        Leaderless lock:
        - Acquire succeeds if lock is absent or expired.
        - Lock auto-expires by lock_until (TTL).
        """
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = self._connect()
            try:
                now = time.time()
                lock_until = now + float(ttl_seconds)
                cur = conn.execute(
                    """
                    UPDATE jobs
                    SET lock_until = ?, lock_owner = ?, updated_at = ?
                    WHERE id = ?
                      AND (lock_until IS NULL OR lock_until <= ?);
                    """,
                    (float(lock_until), str(owner), float(now), str(job_id), float(now)),
                )
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def release_job_lock(self, job_id: str, *, owner: str) -> None:
        """Release lock if owned by `owner` (best-effort)."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> None:
            conn = self._connect()
            try:
                now = time.time()
                conn.execute(
                    """
                    UPDATE jobs
                    SET lock_until = NULL, lock_owner = NULL, updated_at = ?
                    WHERE id = ? AND lock_owner = ?;
                    """,
                    (float(now), str(job_id), str(owner)),
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def create_job_run(self, run: Dict[str, Any]) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            payload = {
                "id": run.get("id") or f"jobrun-{uuid.uuid4().hex[:12]}",
                "job_id": str(run.get("job_id") or ""),
                "scheduled_for": run.get("scheduled_for"),
                "started_at": run.get("started_at"),
                "finished_at": run.get("finished_at"),
                "status": str(run.get("status") or "running"),
                "trace_id": run.get("trace_id"),
                "run_id": run.get("run_id"),
                "error": run.get("error"),
                "result_json": _json_dumps(run.get("result") or {}),
                "created_at": run.get("created_at") or now,
            }
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO job_runs(
                      id,job_id,scheduled_for,started_at,finished_at,status,trace_id,run_id,error,result_json,created_at
                    ) VALUES(
                      :id,:job_id,:scheduled_for,:started_at,:finished_at,:status,:trace_id,:run_id,:error,:result_json,:created_at
                    );
                    """,
                    payload,
                )
                conn.commit()
                return payload
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return self._job_run_row_to_obj(row)

    async def finish_job_run(self, run_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM job_runs WHERE id = ?", (run_id,)).fetchone()
                if not row:
                    return None
                cur = dict(row)
                updated = dict(cur)
                for k in ("scheduled_for", "started_at", "finished_at", "status", "trace_id", "run_id", "error"):
                    if k in patch:
                        updated[k] = patch.get(k)
                if "result" in patch:
                    updated["result_json"] = _json_dumps(patch.get("result") or {})
                conn.execute(
                    """
                    UPDATE job_runs SET
                      scheduled_for=:scheduled_for,
                      started_at=:started_at,
                      finished_at=:finished_at,
                      status=:status,
                      trace_id=:trace_id,
                      run_id=:run_id,
                      error=:error,
                      result_json=:result_json
                    WHERE id=:id;
                    """,
                    {**updated, "id": run_id},
                )
                conn.commit()
                row2 = conn.execute("SELECT * FROM job_runs WHERE id = ?", (run_id,)).fetchone()
                return dict(row2) if row2 else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return self._job_run_row_to_obj(row) if row else None

    async def list_job_runs(self, *, job_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                total_row = conn.execute("SELECT COUNT(1) AS c FROM job_runs WHERE job_id = ?;", (job_id,)).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    """
                    SELECT * FROM job_runs
                    WHERE job_id = ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?;
                    """,
                    (job_id, int(limit), int(offset)),
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        return {
            "items": [self._job_run_row_to_obj(r) for r in (res.get("items") or [])],
            "total": int(res.get("total") or 0),
            "limit": int(limit),
            "offset": int(offset),
        }

    async def get_job_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM job_runs WHERE id = ?", (str(run_id),)).fetchone()
                if not row:
                    return None
                return dict(row)
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return self._job_run_row_to_obj(row) if row else None

    # ---------------------------------------------------------------------
    # Roadmap-4: Skill Packs + Long-term Memory (minimal)
    # ---------------------------------------------------------------------

