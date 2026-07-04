"""
TenantMixin — extracted from ExecutionStore global_mixin.py.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
import anyio
from ._base import _json_dumps, _json_loads


class TenantMixin:
    """Extracted from ExecutionStore."""
    async def upsert_tenant(self, *, tenant_id: str, name: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row0 = conn.execute("SELECT tenant_id, created_at FROM tenants WHERE tenant_id=?;", (str(tenant_id),)).fetchone()
                created_at = float(row0["created_at"]) if row0 and row0.get("created_at") else float(now)
                conn.execute(
                    """
                    INSERT INTO tenants(tenant_id, name, metadata_json, created_at, updated_at)
                    VALUES(?,?,?,?,?)
                    ON CONFLICT(tenant_id) DO UPDATE SET
                      name=excluded.name,
                      metadata_json=excluded.metadata_json,
                      updated_at=excluded.updated_at;
                    """,
                    (str(tenant_id), str(name or tenant_id), _json_dumps(metadata or {}), created_at, float(now)),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM tenants WHERE tenant_id=?;", (str(tenant_id),)).fetchone()
                return dict(row) if row else {}
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {
            "tenant_id": row.get("tenant_id"),
            "name": row.get("name"),
            "metadata": _json_loads(row.get("metadata_json")) or {},
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    async def list_tenants(self, *, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                total = int(conn.execute("SELECT COUNT(1) FROM tenants;").fetchone()[0])
                rows = conn.execute("SELECT * FROM tenants ORDER BY updated_at DESC LIMIT ? OFFSET ?;", (int(limit), int(offset))).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items = []
        for r in res.get("items") or []:
            items.append(
                {
                    "tenant_id": r.get("tenant_id"),
                    "name": r.get("name"),
                    "metadata": _json_loads(r.get("metadata_json")) or {},
                    "created_at": r.get("created_at"),
                    "updated_at": r.get("updated_at"),
                }
            )
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}
