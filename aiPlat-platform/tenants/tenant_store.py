"""TenantStore — tenant quota / usage / policy persistence (P0-A3 migration).

Ownership of the tenant_quotas / tenant_usage_ledger / tenant_policies tables
moved from core ExecutionStore to the platform layer (architecture: multi-
tenant governance belongs to platform; core stays kernel-agnostic, §5.29).

- Same SQLite DB file as core ExecutionStore (AIPLAT_EXECUTION_DB_PATH or
  ~/.aiplat/aiplat_executions.sqlite3) → zero data migration, same tables.
- Method bodies are exact copies of the former core mixins (quota_mixin /
  audit_mixin) — call-site semantics unchanged.
- Injected into core via ``set_tenant_store()`` at platform mount
  (apps.fde __init__) so core consumers (policy gate, llm accounting)
  resolve it through the protocol registry.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

import anyio

logger = logging.getLogger(__name__)


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _json_loads(s: Optional[str]) -> Any:
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


def _default_db_path() -> str:
    return os.environ.get(
        "AIPLAT_EXECUTION_DB_PATH",
        os.path.join(os.path.expanduser("~"), ".aiplat", "aiplat_executions.sqlite3"),
    )


class TenantStore:
    """Tenant quota / usage / policy store (implements core TenantStoreProtocol)."""

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or _default_db_path()
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.row_factory = sqlite3.Row
        return conn

    async def init(self) -> None:
        """Create tenant tables if missing (idempotent, same DB as ExecutionStore)."""
        if self._initialized:
            return

        def _sync() -> None:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tenant_quotas (
                      tenant_id TEXT PRIMARY KEY,
                      version INTEGER NOT NULL,
                      quota_json TEXT NOT NULL,
                      updated_at REAL NOT NULL
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tenant_quotas_updated ON tenant_quotas(updated_at DESC);"
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tenant_usage_ledger (
                      tenant_id TEXT,
                      day TEXT NOT NULL,           -- YYYY-MM-DD (UTC)
                      metric_key TEXT NOT NULL,    -- tool_calls|llm_total_tokens|runs_started|external_access
                      value REAL NOT NULL,
                      updated_at REAL NOT NULL,
                      PRIMARY KEY(tenant_id, day, metric_key)
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tenant_policies (
                      tenant_id TEXT PRIMARY KEY,
                      version INTEGER NOT NULL,
                      policy_json TEXT NOT NULL,
                      updated_at REAL NOT NULL
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tenant_policies_updated ON tenant_policies(updated_at DESC);"
                )
                conn.commit()
            except Exception as e:  # noqa: BLE001 — DDL best-effort, table may already exist
                logger.debug("TenantStore init: %s", e, exc_info=True)
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)
        self._initialized = True

    # ==================== Tenant Quotas ====================

    async def get_tenant_quota(self, *, tenant_id: str) -> Optional[Dict[str, Any]]:
        await self.init()

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
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

    async def upsert_tenant_quota(
        self, *, tenant_id: str, quota: Dict[str, Any], version: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Upsert tenant quota config.
        If version is provided, treat it as optimistic concurrency: update only when current version matches.
        """
        await self.init()

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
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

    # ==================== Tenant Usage ====================

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

        def _utc_day() -> str:
            return time.strftime("%Y-%m-%d", time.gmtime())

        def _sync() -> Dict[str, Any]:
            d = str(day or _utc_day())
            now = float(time.time())
            conn = self._connect()
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
        self, *, tenant_id: str, day: str, metric_key: str
    ) -> float:
        await self.init()

        def _sync() -> float:
            conn = self._connect()
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

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
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

    # ==================== Tenant Policies ====================

    async def get_tenant_policy(self, *, tenant_id: str) -> Optional[Dict[str, Any]]:
        await self.init()

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT tenant_id, version, policy_json, updated_at FROM tenant_policies WHERE tenant_id=? LIMIT 1",
                    (str(tenant_id),),
                ).fetchone()
                if not row:
                    return None
                return {
                    "tenant_id": row["tenant_id"],
                    "version": int(row["version"]),
                    "policy": _json_loads(row["policy_json"]) or {},
                    "updated_at": row["updated_at"],
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def upsert_tenant_policy(
        self, *, tenant_id: str, policy: Dict[str, Any], version: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Upsert a tenant policy.
        If version is provided, treat it as optimistic concurrency: update only when current version matches.
        """
        await self.init()

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            try:
                current = conn.execute(
                    "SELECT version FROM tenant_policies WHERE tenant_id=? LIMIT 1", (str(tenant_id),)
                ).fetchone()
                cur_ver = int(current["version"]) if current else 0
                if version is not None and current and int(version) != cur_ver:
                    raise ValueError("version_conflict")
                next_ver = cur_ver + 1
                now = float(time.time())
                conn.execute(
                    """
                    INSERT INTO tenant_policies(tenant_id, version, policy_json, updated_at)
                    VALUES(?, ?, ?, ?)
                    ON CONFLICT(tenant_id) DO UPDATE SET
                      version=excluded.version,
                      policy_json=excluded.policy_json,
                      updated_at=excluded.updated_at;
                    """,
                    (str(tenant_id), int(next_ver), _json_dumps(policy or {}), now),
                )
                conn.commit()
                return {"tenant_id": str(tenant_id), "version": int(next_ver), "policy": policy or {}, "updated_at": now}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_tenant_policies(
        self, *, limit: int = 100, offset: int = 0
    ) -> Dict[str, Any]:
        await self.init()

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            try:
                total = conn.execute("SELECT COUNT(1) FROM tenant_policies").fetchone()[0]
                rows = conn.execute(
                    """
                    SELECT tenant_id, version, policy_json, updated_at
                    FROM tenant_policies
                    ORDER BY updated_at DESC
                    LIMIT ? OFFSET ?;
                    """,
                    (int(limit), int(offset)),
                ).fetchall()
                items = []
                for r in rows:
                    items.append(
                        {
                            "tenant_id": r["tenant_id"],
                            "version": int(r["version"]),
                            "policy": _json_loads(r["policy_json"]) or {},
                            "updated_at": r["updated_at"],
                        }
                    )
                return {"items": items, "total": int(total), "limit": int(limit), "offset": int(offset)}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)
