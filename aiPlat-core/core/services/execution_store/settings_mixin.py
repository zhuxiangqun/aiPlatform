"""
SettingsMixin — extracted from ExecutionStore global_mixin.py.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
from ._base import _json_dumps, _json_loads


class SettingsMixin:
    """Extracted from ExecutionStore."""
    # ==================== Global Settings & Tenants ====================
    async def upsert_global_setting(self, *, key: str, value: Dict[str, Any]) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                conn.execute(
                    """
                    INSERT INTO global_settings(key, value_json, updated_at)
                    VALUES(?,?,?)
                    ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at;
                    """,
                    (str(key), _json_dumps(value or {}), float(now)),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM global_settings WHERE key=?;", (str(key),)).fetchone()
                return dict(row) if row else {}
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {"key": row.get("key"), "value": _json_loads(row.get("value_json")) or {}, "updated_at": row.get("updated_at")}

    async def get_global_setting(self, *, key: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM global_settings WHERE key=?;", (str(key),)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {"key": row.get("key"), "value": _json_loads(row.get("value_json")) or {}, "updated_at": row.get("updated_at")}

    def get_global_setting_sync(self, *, key: str) -> Optional[Dict[str, Any]]:
        """Synchronous helper; mirrors get_global_setting() SQL.

        NOTE: Assumes init() has been called during startup (normal server flow).
        """
        db_path = self._config.db_path
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM global_settings WHERE key=?;", (str(key),)).fetchone()
            if not row:
                return None
            d = dict(row)
            return {"key": d.get("key"), "value": _json_loads(d.get("value_json")) or {}, "updated_at": d.get("updated_at")}
        finally:
            conn.close()

    # ---------------------------------------------------------------------
    # Tenants (minimal registry)
    # ---------------------------------------------------------------------

