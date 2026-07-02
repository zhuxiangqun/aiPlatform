"""
PluginMixin — extracted from ExecutionStore deploy_mixin.py.

Entity-specific CRUD methods.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
from ._base import _json_dumps, _json_loads


class PluginMixin:
    """Extracted from ExecutionStore."""
    # ==================== Plugins (PR-11) ====================

    async def upsert_plugin(
        self,
        *,
        tenant_id: Optional[str],
        plugin_id: str,
        name: Optional[str] = None,
        version: Optional[str] = None,
        enabled: bool = False,
        manifest: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = float(time.time())
            rec = {
                "tenant_id": str(tenant_id or ""),
                "plugin_id": str(plugin_id),
                "name": str(name) if name is not None else None,
                "version": str(version) if version is not None else None,
                "enabled": 1 if bool(enabled) else 0,
                "manifest_json": _json_dumps(manifest or {}),
                "metadata_json": _json_dumps(metadata or {}),
                "created_at": now,
                "updated_at": now,
            }
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO plugins(
                      tenant_id, plugin_id, name, version, enabled, manifest_json, metadata_json, created_at, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(tenant_id, plugin_id) DO UPDATE SET
                      name=excluded.name,
                      version=excluded.version,
                      enabled=excluded.enabled,
                      manifest_json=excluded.manifest_json,
                      metadata_json=excluded.metadata_json,
                      updated_at=excluded.updated_at;
                    """,
                    (
                        rec["tenant_id"],
                        rec["plugin_id"],
                        rec["name"],
                        rec["version"],
                        rec["enabled"],
                        rec["manifest_json"],
                        rec["metadata_json"],
                        rec["created_at"],
                        rec["updated_at"],
                    ),
                )
                # Best-effort: keep version history (idempotent by PK)
                try:
                    if rec.get("version"):
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO plugin_versions(
                              tenant_id, plugin_id, version, manifest_json, metadata_json, created_at
                            ) VALUES(?,?,?,?,?,?);
                            """,
                            (
                                rec["tenant_id"],
                                rec["plugin_id"],
                                rec["version"],
                                rec["manifest_json"],
                                rec["metadata_json"],
                                rec["updated_at"],
                            ),
                        )
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {**row, "manifest": _json_loads(row.get("manifest_json")) or {}, "metadata": _json_loads(row.get("metadata_json")) or {}}

    async def list_plugin_versions(self, *, tenant_id: Optional[str], plugin_id: str, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                total_row = conn.execute(
                    "SELECT COUNT(1) AS c FROM plugin_versions WHERE tenant_id=? AND plugin_id=?",
                    (str(tenant_id or ""), str(plugin_id)),
                ).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    """
                    SELECT * FROM plugin_versions
                    WHERE tenant_id=? AND plugin_id=?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?;
                    """,
                    (str(tenant_id or ""), str(plugin_id), int(limit), int(offset)),
                ).fetchall()
                items = []
                for r in rows:
                    d = dict(r)
                    d["manifest"] = _json_loads(d.get("manifest_json")) or {}
                    d["metadata"] = _json_loads(d.get("metadata_json")) or {}
                    items.append(d)
                return {"items": items, "total": total, "limit": int(limit), "offset": int(offset)}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_plugin_version(self, *, tenant_id: Optional[str], plugin_id: str, version: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM plugin_versions WHERE tenant_id=? AND plugin_id=? AND version=?",
                    (str(tenant_id or ""), str(plugin_id), str(version)),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {**row, "manifest": _json_loads(row.get("manifest_json")) or {}, "metadata": _json_loads(row.get("metadata_json")) or {}}

