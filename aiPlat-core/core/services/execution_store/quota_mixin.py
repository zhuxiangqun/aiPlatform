"""
QuotaMixin — extracted from ExecutionStore events_mixin.py.

Auto-generated via Mixin split. Contains entity-specific CRUD methods.

# ARCHITECTURE (P0-A3 resolved 2026-08-18): core execution_store is the data
# storage layer for tenant_quotas; aiPlat-platform/api/routers/quota.py is the
# business API layer (migrated from core routers). This split — storage in core
# (via CoreFacade/execution_store), business logic in platform — matches the
# app→platform→core dependency rule: platform does not own DB tables, it
# consumes core storage through the facade. Not deprecated.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
import anyio
import uuid
from ._base import _json_dumps, _json_loads


class QuotaMixin:
    """Extracted from ExecutionStore."""
    # ==================== Tenant Quotas / Usage Ledger (PR-12) ====================

    async def get_tenant_quota(self, *, tenant_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT tenant_id, version, quota_json, updated_at FROM tenant_quotas WHERE tenant_id=? LIMIT 1",
                    (str(tenant_id),),
                ).fetchone()
                if not row:
                    return None
                return {
                    "tenant_id": row["tenant_id"],
                    "version": int(row["version"]),
                    "quota": _json_loads(row["quota_json"]) or {},
                    "updated_at": row["updated_at"],
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def upsert_tenant_quota(self, *, tenant_id: str, quota: Dict[str, Any], version: Optional[int] = None) -> Dict[str, Any]:
        """
        Upsert tenant quota config.
        If version is provided, treat it as optimistic concurrency: update only when current version matches.
        """
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                current = conn.execute(
                    "SELECT version FROM tenant_quotas WHERE tenant_id=? LIMIT 1", (str(tenant_id),)
                ).fetchone()
                cur_ver = int(current["version"]) if current else 0
                if version is not None and current and int(version) != cur_ver:
                    raise ValueError("version_conflict")
                next_ver = cur_ver + 1
                now = float(time.time())
                conn.execute(
                    """
                    INSERT INTO tenant_quotas(tenant_id, version, quota_json, updated_at)
                    VALUES(?, ?, ?, ?)
                    ON CONFLICT(tenant_id) DO UPDATE SET
                      version=excluded.version,
                      quota_json=excluded.quota_json,
                      updated_at=excluded.updated_at;
                    """,
                    (str(tenant_id), int(next_ver), _json_dumps(quota or {}), now),
                )
                conn.commit()
                return {"tenant_id": str(tenant_id), "version": int(next_ver), "quota": quota or {}, "updated_at": now}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def add_tenant_usage(
        self,
        *,
        tenant_id: str,
        metric_key: str,
        amount: float,
        day: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Increment a (tenant, day, metric_key) counter. day defaults to UTC date."""
        await self.init()
        db_path = self._config.db_path

        def _utc_day() -> str:
            return time.strftime("%Y-%m-%d", time.gmtime())

        def _sync() -> Dict[str, Any]:
            d = str(day or _utc_day())
            now = float(time.time())
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                conn.execute(
                    """
                    INSERT INTO tenant_usage_ledger(tenant_id, day, metric_key, value, updated_at)
                    VALUES(?, ?, ?, ?, ?)
                    ON CONFLICT(tenant_id, day, metric_key) DO UPDATE SET
                      value = tenant_usage_ledger.value + excluded.value,
                      updated_at = excluded.updated_at;
                    """,
                    (str(tenant_id), d, str(metric_key), float(amount), now),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT tenant_id, day, metric_key, value, updated_at FROM tenant_usage_ledger WHERE tenant_id=? AND day=? AND metric_key=?",
                    (str(tenant_id), d, str(metric_key)),
                ).fetchone()
                return dict(row) if row else {"tenant_id": str(tenant_id), "day": d, "metric_key": str(metric_key), "value": float(amount), "updated_at": now}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_tenant_usage(
        self,
        *,
        tenant_id: str,
        day: str,
        metric_key: str,
    ) -> float:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> float:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT value FROM tenant_usage_ledger WHERE tenant_id=? AND day=? AND metric_key=? LIMIT 1",
                    (str(tenant_id), str(day), str(metric_key)),
                ).fetchone()
                return float(row["value"]) if row and row["value"] is not None else 0.0
            finally:
                conn.close()

        return float(await anyio.to_thread.run_sync(_sync))

    async def list_tenant_usage(
        self,
        *,
        tenant_id: str,
        day_start: Optional[str] = None,
        day_end: Optional[str] = None,
        metric_key: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                clauses = ["tenant_id=?"]
                params: List[Any] = [str(tenant_id)]
                if day_start:
                    clauses.append("day >= ?")
                    params.append(str(day_start))
                if day_end:
                    clauses.append("day <= ?")
                    params.append(str(day_end))
                if metric_key:
                    clauses.append("metric_key = ?")
                    params.append(str(metric_key))
                where = "WHERE " + " AND ".join(clauses)
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM tenant_usage_ledger {where};", tuple(params)).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT tenant_id, day, metric_key, value, updated_at FROM tenant_usage_ledger {where} ORDER BY day DESC, metric_key ASC LIMIT ? OFFSET ?;",
                    tuple(params + [int(limit), int(offset)]),
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total, "limit": int(limit), "offset": int(offset)}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    # ==================== Connector Delivery Attempts / DLQ (PR-12) ====================

    async def add_connector_delivery_attempt(
        self,
        *,
        connector: str,
        tenant_id: Optional[str],
        run_id: Optional[str],
        attempt: int,
        url: str,
        status: str,
        response_status: Optional[int] = None,
        error: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = float(time.time())
            aid = f"cda-{uuid.uuid4().hex[:12]}"
            rec = {
                "id": aid,
                "connector": str(connector),
                "tenant_id": str(tenant_id) if tenant_id else None,
                "run_id": str(run_id) if run_id else None,
                "attempt": int(attempt),
                "url": str(url),
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
                    INSERT INTO connector_delivery_attempts(
                      id, connector, tenant_id, run_id, attempt, url, status, response_status, error, payload_json, created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        rec["id"],
                        rec["connector"],
                        rec["tenant_id"],
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

    async def list_connector_delivery_attempts(
        self,
        *,
        connector: Optional[str] = None,
        tenant_id: Optional[str] = None,
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
                if connector:
                    clauses.append("connector=?")
                    params.append(str(connector))
                if tenant_id:
                    clauses.append("tenant_id=?")
                    params.append(str(tenant_id))
                if run_id:
                    clauses.append("run_id=?")
                    params.append(str(run_id))
                if status:
                    clauses.append("status=?")
                    params.append(str(status))
                where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
                total_row = conn.execute(
                    f"SELECT COUNT(1) AS c FROM connector_delivery_attempts {where};", tuple(params)
                ).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT * FROM connector_delivery_attempts {where} ORDER BY created_at DESC LIMIT ? OFFSET ?;",
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

    async def enqueue_connector_delivery_dlq(
        self,
        *,
        connector: str,
        tenant_id: Optional[str],
        run_id: Optional[str],
        url: str,
        payload: Dict[str, Any],
        attempts: int,
        error: str,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = float(time.time())
            did = f"cdlq-{uuid.uuid4().hex[:12]}"
            rec = {
                "id": did,
                "connector": str(connector),
                "tenant_id": str(tenant_id) if tenant_id else None,
                "run_id": str(run_id) if run_id else None,
                "url": str(url),
                "payload_json": _json_dumps(payload or {}),
                "attempts": int(attempts),
                "error": str(error),
                "status": "pending",
                "created_at": now,
                "resolved_at": None,
            }
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO connector_delivery_dlq(
                      id, connector, tenant_id, run_id, url, payload_json, attempts, error, status, created_at, resolved_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        rec["id"],
                        rec["connector"],
                        rec["tenant_id"],
                        rec["run_id"],
                        rec["url"],
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
        return {**row, "payload": _json_loads(row.get("payload_json")) or {}}

    async def get_connector_delivery_dlq_item(self, dlq_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM connector_delivery_dlq WHERE id=? LIMIT 1", (str(dlq_id),)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {**row, "payload": _json_loads(row.get("payload_json")) or {}}

    async def list_connector_delivery_dlq(
        self,
        *,
        status: Optional[str] = None,
        tenant_id: Optional[str] = None,
        connector: Optional[str] = None,
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
                    clauses.append("status=?")
                    params.append(str(status))
                if tenant_id:
                    clauses.append("tenant_id=?")
                    params.append(str(tenant_id))
                if connector:
                    clauses.append("connector=?")
                    params.append(str(connector))
                where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM connector_delivery_dlq {where};", tuple(params)).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT * FROM connector_delivery_dlq {where} ORDER BY created_at DESC LIMIT ? OFFSET ?;",
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

    async def resolve_connector_delivery_dlq_item(self, dlq_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            now = float(time.time())
            conn = self._connect()
            try:
                cur = conn.execute(
                    "UPDATE connector_delivery_dlq SET status='resolved', resolved_at=? WHERE id=? AND status='pending';",
                    (now, str(dlq_id)),
                )
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return bool(await anyio.to_thread.run_sync(_sync))

    async def delete_connector_delivery_dlq_item(self, dlq_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM connector_delivery_dlq WHERE id=?;", (str(dlq_id),))
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return bool(await anyio.to_thread.run_sync(_sync))

