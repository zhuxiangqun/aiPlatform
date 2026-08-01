"""
SyscallMixin — extracted from ExecutionStore events_mixin.py.

Auto-generated via Mixin split. Contains entity-specific CRUD methods.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
import anyio
import uuid
from ._base import _derive_change_summary, _json_dumps, _json_loads


class SyscallMixin:
    """Extracted from ExecutionStore."""
    # ==================== Syscall Events (Audit) ====================

    async def _insert_event_raw(self, event: Dict[str, Any]) -> None:
        """Pure SQL INSERT — no EventBus publish, no side effects. Used by DLQ worker."""
        # Best-effort validation
        try:
            from core.harness.observation.event_schema import SyscallEvent
            SyscallEvent.model_validate(event)
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        await self.init()
        db_path = self._config.db_path

        error_code = event.get("error_code")
        if not error_code:
            try:
                err_obj = event.get("error") if isinstance(event.get("error"), dict) else None
                if isinstance(err_obj, dict) and err_obj.get("code"):
                    error_code = err_obj.get("code")
                else:
                    err_str = event.get("error")
                    if isinstance(err_str, str) and err_str.strip():
                        error_code = err_str.strip().upper().replace(" ", "_")[:64]
            except Exception:
                error_code = None

        payload = (
            event.get("id") or str(uuid.uuid4()),
            event.get("trace_id"),
            event.get("span_id"),
            event.get("run_id"),
            event.get("tenant_id"),
            event.get("kind") or "",
            event.get("name") or "",
            event.get("status") or "",
            event.get("start_time"),
            event.get("end_time"),
            event.get("duration_ms"),
            _json_dumps(event.get("args") or {}),
            _json_dumps(event.get("result") or {}),
            event.get("error") if isinstance(event.get("error"), str) else _json_dumps(event.get("error") or None),
            error_code,
            event.get("target_type"),
            event.get("target_id"),
            event.get("user_id"),
            event.get("session_id"),
            event.get("approval_request_id"),
            float(event.get("created_at") or time.time()),
            int(event.get("input_tokens") or 0),
            int(event.get("output_tokens") or 0),
            float(event.get("cost") or 0.0),
            event.get("parent_span_id"),
        )

        def _sync():
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO syscall_events(
                      id, trace_id, span_id, run_id, tenant_id, kind, name, status, start_time, end_time, duration_ms,
                      args_json, result_json, error, error_code, target_type, target_id, user_id, session_id,
                      approval_request_id, created_at, input_tokens, output_tokens, cost, parent_span_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    payload,
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def add_syscall_event(self, event: Dict[str, Any]) -> None:
        """Append a syscall audit event (best-effort)."""
        # Best-effort validation via Pydantic schema
        try:
            from core.harness.observation.event_schema import SyscallEvent
            SyscallEvent.model_validate(event)
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        await self.init()
        db_path = self._config.db_path

        # Best-effort normalize error_code for aggregation.
        error_code = event.get("error_code")
        if not error_code:
            try:
                # Prefer structured error object.
                err_obj = event.get("error") if isinstance(event.get("error"), dict) else None
                if isinstance(err_obj, dict) and err_obj.get("code"):
                    error_code = err_obj.get("code")
                else:
                    err_str = event.get("error")
                    if isinstance(err_str, str) and err_str.strip():
                        # Map common cases; fallback to uppercase token.
                        m = err_str.strip().upper().replace(" ", "_")
                        error_code = m[:64]
            except Exception:
                error_code = None

        payload = (
            event.get("id") or str(uuid.uuid4()),
            event.get("trace_id"),
            event.get("span_id"),
            event.get("run_id"),
            event.get("tenant_id"),
            event.get("kind") or "",
            event.get("name") or "",
            event.get("status") or "",
            event.get("start_time"),
            event.get("end_time"),
            event.get("duration_ms"),
            _json_dumps(event.get("args") or {}),
            _json_dumps(event.get("result") or {}),
            event.get("error") if isinstance(event.get("error"), str) else _json_dumps(event.get("error") or None),
            error_code,
            event.get("target_type"),
            event.get("target_id"),
            event.get("user_id"),
            event.get("session_id"),
            event.get("approval_request_id"),
            float(event.get("created_at") or time.time()),
            int(event.get("input_tokens") or 0),
            int(event.get("output_tokens") or 0),
            float(event.get("cost") or 0.0),
            event.get("parent_span_id"),
        )

        def _sync():
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO syscall_events(
                      id, trace_id, span_id, run_id, tenant_id, kind, name, status, start_time, end_time, duration_ms,
                      args_json, result_json, error, error_code, target_type, target_id, user_id, session_id,
                      approval_request_id, created_at, input_tokens, output_tokens, cost, parent_span_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    payload,
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)
        # Publish to real-time observation layer (best-effort, non-blocking)
        try:
            from core.harness.observation.event_bus import EventBus
            publish_event = dict(event)
            publish_event.setdefault("input_tokens", int(event.get("input_tokens") or 0))
            publish_event.setdefault("output_tokens", int(event.get("output_tokens") or 0))
            publish_event.setdefault("cost", float(event.get("cost") or 0.0))
            EventBus.publish(str(event.get("run_id") or ""), publish_event)
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        # Export to OpenTelemetry (best-effort)
        try:
            from core.harness.observation.otel_bridge import export_syscall_as_span
            export_syscall_as_span(event)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    async def add_import_audit(
        self,
        *,
        skill_id: str,
        skill_name: str = "",
        source_type: str = "",
        pattern: str = "",
        adapted: bool = False,
        lint_errors: int = 0,
        lint_warnings: int = 0,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record an import audit event for skill compliance tracking."""
        await self.init()
        db_path = self._config.db_path

        def _sync():
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO import_audits(skill_id, skill_name, source_type, pattern, adapted,
                      lint_errors, lint_warnings, details_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(skill_id),
                        str(skill_name),
                        str(source_type),
                        str(pattern),
                        1 if adapted else 0,
                        int(lint_errors),
                        int(lint_warnings),
                        _json_dumps(details or {}),
                        float(time.time()),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def list_syscall_events(
        self,
        limit: int = 100,
        offset: int = 0,
        tenant_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        run_id: Optional[str] = None,
        kind: Optional[str] = None,
        name: Optional[str] = None,
        status: Optional[str] = None,
        error_contains: Optional[str] = None,
        error_code: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        approval_request_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List syscall events with basic filters (best-effort; no FTS)."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                clauses = []
                params: list = []
                if tenant_id:
                    clauses.append("tenant_id=?")
                    params.append(str(tenant_id))
                if trace_id:
                    clauses.append("trace_id=?")
                    params.append(trace_id)
                if span_id:
                    clauses.append("span_id=?")
                    params.append(span_id)
                if run_id:
                    clauses.append("run_id=?")
                    params.append(run_id)
                if kind:
                    clauses.append("kind=?")
                    params.append(kind)
                if status:
                    clauses.append("status=?")
                    params.append(status)
                if name:
                    clauses.append("name LIKE ?")
                    params.append(f"%{name}%")
                if error_contains:
                    clauses.append("error LIKE ?")
                    params.append(f"%{error_contains}%")
                if error_code:
                    clauses.append("error_code=?")
                    params.append(error_code)
                if target_type:
                    clauses.append("target_type=?")
                    params.append(target_type)
                if target_id:
                    clauses.append("target_id=?")
                    params.append(target_id)
                if approval_request_id:
                    clauses.append("approval_request_id=?")
                    params.append(approval_request_id)
                where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

                total_row = conn.execute(f"SELECT COUNT(*) AS c FROM syscall_events {where_sql}", tuple(params)).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"""
                    SELECT * FROM syscall_events
                    {where_sql}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    tuple(params + [int(limit), int(offset)]),
                ).fetchall()

                items = []
                for r in rows:
                    items.append(
                        {
                            "id": r["id"],
                            "trace_id": r["trace_id"],
                            "span_id": r["span_id"] if "span_id" in r.keys() else None,
                            "parent_span_id": r["parent_span_id"] if "parent_span_id" in r.keys() else None,
                            "run_id": r["run_id"],
                            "kind": r["kind"],
                            "name": r["name"],
                            "status": r["status"],
                            "start_time": r["start_time"],
                            "end_time": r["end_time"],
                            "duration_ms": r["duration_ms"],
                            "args": _json_loads(r["args_json"]) or {},
                            "result": _json_loads(r["result_json"]) or {},
                            "error": r["error"],
                            "error_code": r["error_code"] if "error_code" in r.keys() else None,
                            "target_type": r["target_type"] if "target_type" in r.keys() else None,
                            "target_id": r["target_id"] if "target_id" in r.keys() else None,
                            "user_id": r["user_id"] if "user_id" in r.keys() else None,
                            "session_id": r["session_id"] if "session_id" in r.keys() else None,
                            "tenant_id": r["tenant_id"] if "tenant_id" in r.keys() else None,
                            "approval_request_id": r["approval_request_id"] if "approval_request_id" in r.keys() else None,
                            "input_tokens": r["input_tokens"] if "input_tokens" in r.keys() else 0,
                            "output_tokens": r["output_tokens"] if "output_tokens" in r.keys() else 0,
                            "cost": r["cost"] if "cost" in r.keys() else 0.0,
                            "created_at": r["created_at"],
                        }
                    )
                return {"items": items, "total": total}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ==================== Change Control (Derived from syscall_events) ====================

    async def list_change_controls(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List change controls (grouped by change_id) from syscall_events.

        Source of truth:
          syscall_events(kind='changeset', target_type='change', target_id=change_id)
        """
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                clauses = ["kind='changeset'", "target_type='change'", "target_id IS NOT NULL", "target_id != ''"]
                params: list = []
                if tenant_id:
                    clauses.append("tenant_id=?")
                    params.append(str(tenant_id))
                where = " AND ".join(clauses)
                clauses_e = ["e.kind='changeset'", "e.target_type='change'", "e.target_id IS NOT NULL", "e.target_id != ''"]
                if tenant_id:
                    clauses_e.append("e.tenant_id=?")
                where_e = " AND ".join(clauses_e)

                total_row = conn.execute(f"SELECT COUNT(DISTINCT target_id) AS c FROM syscall_events WHERE {where};", params).fetchone()
                total = int(total_row["c"] if total_row else 0)

                rows = conn.execute(
                    f"""
                    SELECT e.*
                    FROM syscall_events e
                    JOIN (
                      SELECT target_id, MAX(created_at) AS last_ts
                      FROM syscall_events
                      WHERE {where}
                      GROUP BY target_id
                    ) t
                    ON e.target_id = t.target_id AND e.created_at = t.last_ts
                    WHERE {where_e}
                    ORDER BY e.created_at DESC
                    LIMIT ? OFFSET ?;
                    """,
                    [*params, int(limit), int(offset)],
                ).fetchall()

                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        raw = await anyio.to_thread.run_sync(_sync)
        out_items = []
        for r in raw.get("items") or []:
            args = _json_loads(r.get("args_json")) or {}
            result = _json_loads(r.get("result_json")) or {}
            change_id = r.get("target_id")
            latest = {**r, "args": args, "result": result, "change_id": change_id}
            out_items.append({**latest, "summary": _derive_change_summary(latest)})
        return {"items": out_items, "total": int(raw.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    async def get_change_control(
        self,
        *,
        change_id: str,
        limit: int = 200,
        offset: int = 0,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return a change control detail: latest + events."""
        items = await self.list_syscall_events(
            limit=int(limit),
            offset=int(offset),
            tenant_id=tenant_id,
            kind="changeset",
            target_type="change",
            target_id=str(change_id),
        )
        latest = (items.get("items") or [None])[0] if isinstance(items.get("items"), list) and items.get("items") else None
        summary = _derive_change_summary(latest) if isinstance(latest, dict) else _derive_change_summary(None)
        return {"change_id": str(change_id), "latest": latest, "events": {**items, "limit": int(limit), "offset": int(offset)}, "summary": summary}

