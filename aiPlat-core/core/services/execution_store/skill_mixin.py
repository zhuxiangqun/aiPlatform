"""
SkillMixin — extracted from ExecutionStore events_mixin.py.

Auto-generated via Mixin split. Contains entity-specific CRUD methods.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
from ._base import _json_dumps, _json_loads


class SkillMixin:
    """Extracted from ExecutionStore."""
    # ==================== Skill ====================

    async def upsert_skill_execution(self, record: Dict[str, Any]) -> None:
        await self.init()
        db_path = self._config.db_path

        meta = record.get("metadata") or {}
        error_code = record.get("error_code")
        if not error_code:
            try:
                if isinstance(meta, dict) and isinstance(meta.get("error_detail"), dict):
                    error_code = meta.get("error_detail", {}).get("code")
            except Exception:
                error_code = None

        tenant_id = record.get("tenant_id")
        if not tenant_id:
            try:
                if isinstance(meta, dict):
                    tenant_id = meta.get("tenant_id")
            except Exception:
                tenant_id = None

        payload = (
            record.get("id"),
            record.get("skill_id"),
            str(tenant_id) if tenant_id is not None else None,
            record.get("status"),
            _json_dumps(record.get("input")),
            _json_dumps(record.get("output")),
            record.get("error"),
            error_code,
            float(record.get("start_time") or 0.0),
            float(record.get("end_time") or 0.0),
            int(record.get("duration_ms") or 0),
            record.get("user_id"),
            record.get("trace_id"),
            _json_dumps(meta),
            time.time(),
        )

        def _sync():
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO skill_executions
                      (id, skill_id, tenant_id, status, input_json, output_json, error, error_code, start_time, end_time, duration_ms, user_id, trace_id, metadata_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                      skill_id=excluded.skill_id,
                      tenant_id=excluded.tenant_id,
                      status=excluded.status,
                      input_json=excluded.input_json,
                      output_json=excluded.output_json,
                      error=excluded.error,
                      error_code=excluded.error_code,
                      start_time=excluded.start_time,
                      end_time=excluded.end_time,
                      duration_ms=excluded.duration_ms,
                      user_id=excluded.user_id,
                      trace_id=excluded.trace_id,
                      metadata_json=excluded.metadata_json;
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
            conn = self._connect()
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
                    "tenant_id": row["tenant_id"] if "tenant_id" in row.keys() else None,
                    "status": row["status"],
                    "input": _json_loads(row["input_json"]),
                    "output": _json_loads(row["output_json"]),
                    "error": row["error"],
                    "error_code": row["error_code"] if "error_code" in row.keys() else None,
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                    "duration_ms": row["duration_ms"],
                    "user_id": row["user_id"],
                    "trace_id": row["trace_id"] if "trace_id" in row.keys() else None,
                    "metadata": _json_loads(row["metadata_json"]) if "metadata_json" in row.keys() else None,
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_skill_executions(self, skill_id: str, limit: int, offset: int) -> Tuple[List[Dict[str, Any]], int]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Tuple[List[Dict[str, Any]], int]:
            conn = self._connect()
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
                            "tenant_id": row["tenant_id"] if "tenant_id" in row.keys() else None,
                            "status": row["status"],
                            "input": _json_loads(row["input_json"]),
                            "output": _json_loads(row["output_json"]),
                            "error": row["error"],
                            "error_code": row["error_code"] if "error_code" in row.keys() else None,
                            "start_time": row["start_time"],
                            "end_time": row["end_time"],
                            "duration_ms": row["duration_ms"],
                            "user_id": row["user_id"],
                            "trace_id": row["trace_id"] if "trace_id" in row.keys() else None,
                            "metadata": _json_loads(row["metadata_json"]) if "metadata_json" in row.keys() else None,
                        }
                    )
                return items, int(total)
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ---------------------------------------------------------------------
    # Roadmap-3: Jobs/Cron (minimal scheduler persistence)
    # ---------------------------------------------------------------------

    """Skill execution CRUD."""
    pass
