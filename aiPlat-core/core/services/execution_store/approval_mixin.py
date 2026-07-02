"""
ApprovalMixin — extracted from ExecutionStore events_mixin.py.

Auto-generated via Mixin split. Contains entity-specific CRUD methods.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
from ._base import _json_dumps, _json_loads


class ApprovalMixin:
    """Extracted from ExecutionStore."""
    # ==================== Approval Requests ====================

    async def upsert_approval_request(self, record: Dict[str, Any]) -> None:
        await self.init()
        db_path = self._config.db_path

        # PR-08: optional indexed columns
        tenant_id = record.get("tenant_id")
        actor_id = record.get("actor_id")
        actor_role = record.get("actor_role")
        session_id = record.get("session_id")
        run_id = record.get("run_id")

        payload = (
            record.get("request_id"),
            record.get("user_id"),
            record.get("operation"),
            record.get("details"),
            record.get("rule_id"),
            record.get("rule_type"),
            record.get("status"),
            record.get("amount"),
            record.get("batch_size"),
            1 if record.get("is_first_time") else 0,
            float(record.get("created_at") or time.time()),
            float(record.get("updated_at") or time.time()),
            record.get("expires_at"),
            _json_dumps(record.get("metadata") or {}),
            _json_dumps(record.get("result") or {}),
            str(tenant_id) if tenant_id is not None else None,
            str(actor_id) if actor_id is not None else None,
            str(actor_role) if actor_role is not None else None,
            str(session_id) if session_id is not None else None,
            str(run_id) if run_id is not None else None,
        )

        def _sync():
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO approval_requests(
                      request_id, user_id, operation, details, rule_id, rule_type, status,
                      amount, batch_size, is_first_time, created_at, updated_at, expires_at,
                      metadata_json, result_json,
                      tenant_id, actor_id, actor_role, session_id, run_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(request_id) DO UPDATE SET
                      user_id=excluded.user_id,
                      operation=excluded.operation,
                      details=excluded.details,
                      rule_id=excluded.rule_id,
                      rule_type=excluded.rule_type,
                      status=excluded.status,
                      amount=excluded.amount,
                      batch_size=excluded.batch_size,
                      is_first_time=excluded.is_first_time,
                      created_at=excluded.created_at,
                      updated_at=excluded.updated_at,
                      expires_at=excluded.expires_at,
                      metadata_json=excluded.metadata_json,
                      result_json=excluded.result_json,
                      tenant_id=excluded.tenant_id,
                      actor_id=excluded.actor_id,
                      actor_role=excluded.actor_role,
                      session_id=excluded.session_id,
                      run_id=excluded.run_id;
                    """,
                    payload,
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)

    async def get_approval_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM approval_requests WHERE request_id=?", (request_id,)).fetchone()
                if not row:
                    return None
                return {
                    "request_id": row["request_id"],
                    "user_id": row["user_id"],
                    "operation": row["operation"],
                    "details": row["details"],
                    "rule_id": row["rule_id"],
                    "rule_type": row["rule_type"],
                    "status": row["status"],
                    "amount": row["amount"],
                    "batch_size": row["batch_size"],
                    "is_first_time": bool(row["is_first_time"] or 0),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "expires_at": row["expires_at"],
                    "metadata": _json_loads(row["metadata_json"]) or {},
                    "result": _json_loads(row["result_json"]) or None,
                    "tenant_id": row["tenant_id"] if "tenant_id" in row.keys() else None,
                    "actor_id": row["actor_id"] if "actor_id" in row.keys() else None,
                    "actor_role": row["actor_role"] if "actor_role" in row.keys() else None,
                    "session_id": row["session_id"] if "session_id" in row.keys() else None,
                    "run_id": row["run_id"] if "run_id" in row.keys() else None,
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    def get_approval_request_sync(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Synchronous helper for ApprovalManager/guards that run in sync contexts.

        NOTE: This assumes `init()` has been called during application startup (normal server flow).
        It intentionally mirrors `get_approval_request()`'s SQL so semantics stay consistent.
        """
        db_path = self._config.db_path
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM approval_requests WHERE request_id=?", (str(request_id),)).fetchone()
            if not row:
                return None
            return {
                "request_id": row["request_id"],
                "user_id": row["user_id"],
                "operation": row["operation"],
                "details": row["details"],
                "rule_id": row["rule_id"],
                "rule_type": row["rule_type"],
                "status": row["status"],
                "amount": row["amount"],
                "batch_size": row["batch_size"],
                "is_first_time": bool(row["is_first_time"] or 0),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "expires_at": row["expires_at"],
                "metadata": _json_loads(row["metadata_json"]) or {},
                "result": _json_loads(row["result_json"]) or None,
                "tenant_id": row["tenant_id"] if "tenant_id" in row.keys() else None,
                "actor_id": row["actor_id"] if "actor_id" in row.keys() else None,
                "actor_role": row["actor_role"] if "actor_role" in row.keys() else None,
                "session_id": row["session_id"] if "session_id" in row.keys() else None,
                "run_id": row["run_id"] if "run_id" in row.keys() else None,
            }
        finally:
            conn.close()

    async def list_approval_requests(
        self,
        *,
        status: Optional[str] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        run_id: Optional[str] = None,
        operation: Optional[str] = None,
        include_related_counts: bool = False,
        order_by: str = "created_at",
        order_dir: str = "desc",
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
                params: list = []
                if status:
                    clauses.append("status=?")
                    params.append(status)
                if user_id:
                    clauses.append("user_id=?")
                    params.append(user_id)
                if tenant_id is not None:
                    clauses.append("tenant_id=?")
                    params.append(str(tenant_id))
                if actor_id is not None:
                    clauses.append("actor_id=?")
                    params.append(str(actor_id))
                if run_id is not None:
                    clauses.append("run_id=?")
                    params.append(str(run_id))
                if operation is not None:
                    clauses.append("operation=?")
                    params.append(str(operation))
                where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

                total_row = conn.execute(f"SELECT COUNT(*) AS c FROM approval_requests {where_sql}", tuple(params)).fetchone()
                total = int(total_row["c"] if total_row else 0)

                # Ordering: whitelist to avoid SQL injection
                _order_dir = "DESC" if str(order_dir).lower() in ("desc", "d", "-1") else "ASC"
                _order_by = str(order_by or "created_at").lower()
                allowed_order_by = {"created_at", "updated_at", "expires_at", "user_id", "operation", "status"}
                sql_order_by = "created_at" if _order_by not in allowed_order_by else _order_by

                # If ordering by priority_score, we sort in python after enrichment.
                if _order_by == "priority_score":
                    fetch_n = min(max(int(limit) + int(offset), 200), 2000)
                    rows = conn.execute(
                        f"""
                        SELECT * FROM approval_requests
                        {where_sql}
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        tuple(params + [fetch_n]),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        f"""
                        SELECT * FROM approval_requests
                        {where_sql}
                        ORDER BY {sql_order_by} {_order_dir}
                        LIMIT ? OFFSET ?
                        """,
                        tuple(params + [int(limit), int(offset)]),
                    ).fetchall()

                items = []
                now_ts = time.time()
                for r in rows:
                    item = {
                        "request_id": r["request_id"],
                        "user_id": r["user_id"],
                        "operation": r["operation"],
                        "details": r["details"],
                        "rule_id": r["rule_id"],
                        "rule_type": r["rule_type"],
                        "status": r["status"],
                        "amount": r["amount"],
                        "batch_size": r["batch_size"],
                        "is_first_time": bool(r["is_first_time"] or 0),
                        "created_at": r["created_at"],
                        "updated_at": r["updated_at"],
                        "expires_at": r["expires_at"],
                        "metadata": _json_loads(r["metadata_json"]) or {},
                        "result": _json_loads(r["result_json"]) or None,
                        "tenant_id": r["tenant_id"] if "tenant_id" in r.keys() else None,
                        "actor_id": r["actor_id"] if "actor_id" in r.keys() else None,
                        "actor_role": r["actor_role"] if "actor_role" in r.keys() else None,
                        "session_id": r["session_id"] if "session_id" in r.keys() else None,
                        "run_id": r["run_id"] if "run_id" in r.keys() else None,
                    }

                    # Derived metrics for queueing / SLA
                    try:
                        item["age_seconds"] = max(0.0, float(now_ts - float(r["created_at"] or now_ts)))
                    except Exception:
                        item["age_seconds"] = 0.0
                    try:
                        if r["expires_at"] is not None:
                            item["expires_in_seconds"] = float(r["expires_at"] - now_ts)
                        else:
                            item["expires_in_seconds"] = None
                    except Exception:
                        item["expires_in_seconds"] = None

                    if include_related_counts:
                        try:
                            aid = r["request_id"]
                            c1 = conn.execute(
                                "SELECT COUNT(1) AS c FROM syscall_events WHERE approval_request_id=?",
                                (aid,),
                            ).fetchone()
                            c2 = conn.execute(
                                "SELECT COUNT(1) AS c FROM agent_executions WHERE approval_request_id=?",
                                (aid,),
                            ).fetchone()
                            item["related_counts"] = {
                                "syscall_events": int(c1["c"] if c1 else 0),
                                "agent_executions": int(c2["c"] if c2 else 0),
                            }
                        except Exception:
                            item["related_counts"] = {"syscall_events": 0, "agent_executions": 0}

                    # Priority score: higher means more urgent
                    # Heuristic: age + impact + danger (prefer tool metadata.risk_weight when available)
                    meta = item.get("metadata") or {}
                    danger_weight = 0.0
                    try:
                        if isinstance(meta, dict) and "risk_weight" in meta:
                            danger_weight = float(meta.get("risk_weight") or 0.0)
                        else:
                            op = str(item.get("operation") or "")
                            if op.startswith("tool:"):
                                t = op.split(":", 1)[1]
                                if t in ("database", "database_write"):
                                    danger_weight = 50.0
                                elif t in ("code", "code_execution"):
                                    danger_weight = 40.0
                                elif t in ("file_operations", "file_write"):
                                    danger_weight = 30.0
                                else:
                                    danger_weight = 10.0
                    except Exception:
                        danger_weight = 0.0
                    age_hours = float(item.get("age_seconds") or 0.0) / 3600.0
                    rel = item.get("related_counts") or {"syscall_events": 0, "agent_executions": 0}
                    impact = float(rel.get("syscall_events", 0)) * 5.0 + float(rel.get("agent_executions", 0)) * 2.0
                    item["priority_score"] = danger_weight + impact + age_hours

                    items.append(item)

                if _order_by == "priority_score":
                    reverse = True if _order_dir == "DESC" else False
                    items.sort(key=lambda x: float(x.get("priority_score") or 0.0), reverse=reverse)
                    items = items[int(offset) : int(offset) + int(limit)]
                return {"items": items, "total": total}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_change_linkages_for_approval_request_ids(self, request_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Best-effort mapping approval_request_id -> {change_id, run_id, trace_id, created_at}.
        Source: syscall_events(kind='changeset', target_type='change', approval_request_id in request_ids)
        """
        await self.init()
        ids = [str(x) for x in (request_ids or []) if isinstance(x, str) and x.strip()]
        if not ids:
            return {}
        db_path = self._config.db_path

        def _sync() -> Dict[str, Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                placeholders = ",".join(["?"] * len(ids))
                rows = conn.execute(
                    f"""
                    SELECT e.approval_request_id, e.target_id AS change_id, e.run_id, e.trace_id, e.created_at
                    FROM syscall_events e
                    JOIN (
                      SELECT approval_request_id, MAX(created_at) AS last_ts
                      FROM syscall_events
                      WHERE kind='changeset'
                        AND target_type='change'
                        AND approval_request_id IN ({placeholders})
                        AND approval_request_id IS NOT NULL
                        AND approval_request_id != ''
                        AND target_id IS NOT NULL
                        AND target_id != ''
                      GROUP BY approval_request_id
                    ) t
                    ON e.approval_request_id = t.approval_request_id AND e.created_at = t.last_ts
                    WHERE e.kind='changeset' AND e.target_type='change';
                    """,
                    tuple(ids),
                ).fetchall()
                out: Dict[str, Dict[str, Any]] = {}
                for r in rows:
                    aid = r["approval_request_id"]
                    if not aid:
                        continue
                    out[str(aid)] = {
                        "change_id": r["change_id"],
                        "run_id": r["run_id"],
                        "trace_id": r["trace_id"],
                        "created_at": r["created_at"],
                    }
                return out
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

