"""
AgentMixin — extracted from ExecutionStore events_mixin.py.

Auto-generated via Mixin split. Contains entity-specific CRUD methods.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
from ._base import _json_dumps, _json_loads


class AgentMixin:
    """Extracted from ExecutionStore."""
    # ==================== Agent ====================

    async def upsert_agent_execution(self, record: Dict[str, Any]) -> None:
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
            record.get("agent_id"),
            str(tenant_id) if tenant_id is not None else None,
            record.get("status"),
            _json_dumps(record.get("input")),
            _json_dumps(record.get("output")),
            record.get("error"),
            error_code,
            float(record.get("start_time") or 0.0),
            float(record.get("end_time") or 0.0),
            int(record.get("duration_ms") or 0),
            record.get("trace_id"),
            _json_dumps(meta),
            record.get("approval_request_id"),
            time.time(),
        )

        def _sync():
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO agent_executions
                      (id, agent_id, tenant_id, status, input_json, output_json, error, error_code, start_time, end_time, duration_ms, trace_id, metadata_json, approval_request_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                      agent_id=excluded.agent_id,
                      tenant_id=excluded.tenant_id,
                      status=excluded.status,
                      input_json=excluded.input_json,
                      output_json=excluded.output_json,
                      error=excluded.error,
                      error_code=excluded.error_code,
                      start_time=excluded.start_time,
                      end_time=excluded.end_time,
                      duration_ms=excluded.duration_ms,
                      trace_id=excluded.trace_id,
                      metadata_json=excluded.metadata_json,
                      approval_request_id=excluded.approval_request_id;
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
            conn = self._connect()
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
                    "tenant_id": row["tenant_id"] if "tenant_id" in row.keys() else None,
                    "status": row["status"],
                    "input": _json_loads(row["input_json"]),
                    "output": _json_loads(row["output_json"]),
                    "error": row["error"],
                    "error_code": row["error_code"] if "error_code" in row.keys() else None,
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                    "duration_ms": row["duration_ms"],
                    "trace_id": row["trace_id"] if "trace_id" in row.keys() else None,
                    "metadata": _json_loads(row["metadata_json"]) if "metadata_json" in row.keys() else None,
                    "approval_request_id": row["approval_request_id"] if "approval_request_id" in row.keys() else None,
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_agent_executions_by_approval_request_id(
        self,
        approval_request_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """List agent executions associated with an approval_request_id."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                total_row = conn.execute(
                    "SELECT COUNT(1) AS c FROM agent_executions WHERE approval_request_id = ?",
                    (approval_request_id,),
                ).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    """
                    SELECT * FROM agent_executions
                    WHERE approval_request_id = ?
                    ORDER BY start_time DESC
                    LIMIT ? OFFSET ?;
                    """,
                    (approval_request_id, int(limit), int(offset)),
                ).fetchall()
                items: List[Dict[str, Any]] = []
                for row in rows:
                    items.append(
                        {
                            "id": row["id"],
                            "agent_id": row["agent_id"],
                            "tenant_id": row["tenant_id"] if "tenant_id" in row.keys() else None,
                            "status": row["status"],
                            "input": _json_loads(row["input_json"]),
                            "output": _json_loads(row["output_json"]),
                            "error": row["error"],
                            "error_code": row["error_code"] if "error_code" in row.keys() else None,
                            "start_time": row["start_time"],
                            "end_time": row["end_time"],
                            "duration_ms": row["duration_ms"],
                            "trace_id": row["trace_id"] if "trace_id" in row.keys() else None,
                            "metadata": _json_loads(row["metadata_json"]) if "metadata_json" in row.keys() else None,
                            "approval_request_id": row["approval_request_id"] if "approval_request_id" in row.keys() else None,
                        }
                    )
                return {"items": items, "total": total}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ---------------------------------------------------------------------
    # Phase 6 (placeholder): learning artifacts (evaluation/feedback/evolution)
    # ---------------------------------------------------------------------

    async def upsert_learning_artifact(self, record: Dict[str, Any]) -> None:
        await self.init()
        db_path = self._config.db_path

        payload = (
            record.get("artifact_id"),
            record.get("kind") or "",
            record.get("target_type") or "",
            record.get("target_id") or "",
            record.get("version") or "",
            record.get("status") or "draft",
            record.get("trace_id"),
            record.get("run_id"),
            _json_dumps(record.get("payload") or {}),
            _json_dumps(record.get("metadata") or {}),
            float(record.get("created_at") or time.time()),
        )

        def _sync() -> None:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO learning_artifacts(
                      artifact_id, kind, target_type, target_id, version, status,
                      trace_id, run_id, payload_json, metadata_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(artifact_id) DO UPDATE SET
                      kind=excluded.kind,
                      target_type=excluded.target_type,
                      target_id=excluded.target_id,
                      version=excluded.version,
                      status=excluded.status,
                      trace_id=excluded.trace_id,
                      run_id=excluded.run_id,
                      payload_json=excluded.payload_json,
                      metadata_json=excluded.metadata_json,
                      created_at=excluded.created_at;
                    """,
                    payload,
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def get_learning_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM learning_artifacts WHERE artifact_id=?",
                    (artifact_id,),
                ).fetchone()
                if not row:
                    return None
                return {
                    "artifact_id": row["artifact_id"],
                    "kind": row["kind"],
                    "target_type": row["target_type"],
                    "target_id": row["target_id"],
                    "version": row["version"],
                    "status": row["status"],
                    "trace_id": row["trace_id"],
                    "run_id": row["run_id"],
                    "payload": _json_loads(row["payload_json"]),
                    "metadata": _json_loads(row["metadata_json"]),
                    "created_at": row["created_at"],
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_learning_artifacts(
        self,
        *,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        kind: Optional[str] = None,
        status: Optional[str] = None,
        trace_id: Optional[str] = None,
        run_id: Optional[str] = None,
        metadata_contains: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                clauses: List[str] = []
                params: List[Any] = []
                if target_type:
                    clauses.append("target_type=?")
                    params.append(target_type)
                if target_id:
                    clauses.append("target_id=?")
                    params.append(target_id)
                if kind:
                    clauses.append("kind=?")
                    params.append(kind)
                if status:
                    clauses.append("status=?")
                    params.append(status)
                if trace_id:
                    clauses.append("trace_id=?")
                    params.append(trace_id)
                if run_id:
                    clauses.append("run_id=?")
                    params.append(run_id)
                if metadata_contains:
                    clauses.append("metadata_json LIKE ?")
                    params.append(f"%{str(metadata_contains)}%")
                where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

                total_row = conn.execute(
                    f"SELECT COUNT(1) AS c FROM learning_artifacts {where};",
                    tuple(params),
                ).fetchone()
                total = int(total_row["c"] if total_row else 0)

                rows = conn.execute(
                    f"""
                    SELECT * FROM learning_artifacts
                    {where}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?;
                    """,
                    tuple(params + [int(limit), int(offset)]),
                ).fetchall()
                items: List[Dict[str, Any]] = []
                for row in rows:
                    items.append(
                        {
                            "artifact_id": row["artifact_id"],
                            "kind": row["kind"],
                            "target_type": row["target_type"],
                            "target_id": row["target_id"],
                            "version": row["version"],
                            "status": row["status"],
                            "trace_id": row["trace_id"],
                            "run_id": row["run_id"],
                            "payload": _json_loads(row["payload_json"]),
                            "metadata": _json_loads(row["metadata_json"]),
                            "created_at": row["created_at"],
                        }
                    )
                return {"total": total, "items": items, "limit": limit, "offset": offset}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_agent_history(self, agent_id: str, limit: int, offset: int) -> Tuple[List[Dict[str, Any]], int]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Tuple[List[Dict[str, Any]], int]:
            conn = self._connect()
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
                            "error_code": row["error_code"] if "error_code" in row.keys() else None,
                            "start_time": row["start_time"],
                            "end_time": row["end_time"],
                            "duration_ms": row["duration_ms"],
                            "trace_id": row["trace_id"] if "trace_id" in row.keys() else None,
                            "metadata": _json_loads(row["metadata_json"]) if "metadata_json" in row.keys() else None,
                            "approval_request_id": row["approval_request_id"] if "approval_request_id" in row.keys() else None,
                        }
                    )
                return items, int(total)
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

