from __future__ import annotations

import json
import os
import sqlite3
import time
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import anyio


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def _json_loads(s: Optional[str]) -> Any:
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return s


@dataclass(frozen=True)
class ConfigRegistryKey:
    asset_type: str  # e.g. skill_spec_v2_schema, permissions_catalog
    scope: str  # workspace | engine
    tenant_id: str
    channel: str  # stable | canary


class ConfigRegistryStore:
    """
    Minimal config registry stored in the execution DB (SQLite).

    Design goals:
    - publish/rollback (stable/canary)
    - multi-tenant isolation
    - audit trail of published versions
    """

    def __init__(self, db_path: str):
        self._db_path = str(db_path)
        self._init_lock = anyio.Lock()
        self._inited = False

    async def init(self) -> None:
        async with self._init_lock:
            if self._inited:
                return
            os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)

            def _init_sync() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute("PRAGMA journal_mode=WAL;")
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS config_assets (
                          asset_type TEXT NOT NULL,
                          scope TEXT NOT NULL,
                          tenant_id TEXT NOT NULL,
                          version TEXT NOT NULL,
                          payload_json TEXT NOT NULL,
                          created_at REAL NOT NULL,
                          created_by TEXT,
                          note TEXT,
                          PRIMARY KEY(asset_type, scope, tenant_id, version)
                        );
                        """
                    )
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS config_published (
                          asset_type TEXT NOT NULL,
                          scope TEXT NOT NULL,
                          tenant_id TEXT NOT NULL,
                          channel TEXT NOT NULL,
                          version TEXT NOT NULL,
                          prev_version TEXT,
                          updated_at REAL NOT NULL,
                          updated_by TEXT,
                          note TEXT,
                          PRIMARY KEY(asset_type, scope, tenant_id, channel)
                        );
                        """
                    )
                    conn.commit()
                finally:
                    conn.close()

            await anyio.to_thread.run_sync(_init_sync)
            self._inited = True

    @staticmethod
    def compute_version(payload: Any) -> str:
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:12]

    async def upsert_asset(
        self,
        *,
        asset_type: str,
        scope: str,
        tenant_id: str,
        payload: Any,
        created_by: Optional[str] = None,
        note: Optional[str] = None,
        version: Optional[str] = None,
    ) -> str:
        await self.init()
        v = (version or "").strip() or self.compute_version(payload)
        payload_json = _json_dumps(payload)
        now = time.time()

        def _sync() -> None:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO config_assets(asset_type, scope, tenant_id, version, payload_json, created_at, created_by, note)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(asset_type, scope, tenant_id, version) DO UPDATE SET
                      payload_json=excluded.payload_json,
                      note=COALESCE(excluded.note, config_assets.note);
                    """,
                    (asset_type, scope, tenant_id, v, payload_json, now, created_by, note),
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)
        return v

    async def publish(
        self,
        *,
        key: ConfigRegistryKey,
        payload: Any,
        actor: str,
        note: Optional[str] = None,
        version: Optional[str] = None,
    ) -> str:
        await self.init()
        v = await self.upsert_asset(
            asset_type=key.asset_type,
            scope=key.scope,
            tenant_id=key.tenant_id,
            payload=payload,
            created_by=actor,
            note=note,
            version=version,
        )
        now = time.time()

        def _sync() -> None:
            conn = sqlite3.connect(self._db_path)
            try:
                prev = conn.execute(
                    "SELECT version FROM config_published WHERE asset_type=? AND scope=? AND tenant_id=? AND channel=?",
                    (key.asset_type, key.scope, key.tenant_id, key.channel),
                ).fetchone()
                prev_v = prev[0] if prev else None
                conn.execute(
                    """
                    INSERT INTO config_published(asset_type, scope, tenant_id, channel, version, prev_version, updated_at, updated_by, note)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(asset_type, scope, tenant_id, channel) DO UPDATE SET
                      prev_version=config_published.version,
                      version=excluded.version,
                      updated_at=excluded.updated_at,
                      updated_by=excluded.updated_by,
                      note=excluded.note;
                    """,
                    (key.asset_type, key.scope, key.tenant_id, key.channel, v, prev_v, now, actor, note),
                )
                conn.commit()
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_sync)
        return v

    async def rollback(self, *, key: ConfigRegistryKey, actor: str, note: Optional[str] = None) -> Optional[str]:
        await self.init()
        now = time.time()

        def _sync() -> Optional[str]:
            conn = sqlite3.connect(self._db_path)
            try:
                row = conn.execute(
                    "SELECT version, prev_version FROM config_published WHERE asset_type=? AND scope=? AND tenant_id=? AND channel=?",
                    (key.asset_type, key.scope, key.tenant_id, key.channel),
                ).fetchone()
                if not row:
                    return None
                cur, prev = row[0], row[1]
                if not prev:
                    return cur
                conn.execute(
                    """
                    UPDATE config_published SET
                      version=?,
                      prev_version=?,
                      updated_at=?,
                      updated_by=?,
                      note=?
                    WHERE asset_type=? AND scope=? AND tenant_id=? AND channel=?;
                    """,
                    (prev, cur, now, actor, note, key.asset_type, key.scope, key.tenant_id, key.channel),
                )
                conn.commit()
                return prev
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_published(self, *, key: ConfigRegistryKey) -> Optional[Tuple[str, Any]]:
        await self.init()

        def _sync() -> Optional[Tuple[str, Any]]:
            conn = sqlite3.connect(self._db_path)
            try:
                row = conn.execute(
                    "SELECT version FROM config_published WHERE asset_type=? AND scope=? AND tenant_id=? AND channel=?",
                    (key.asset_type, key.scope, key.tenant_id, key.channel),
                ).fetchone()
                if not row:
                    return None
                v = row[0]
                row2 = conn.execute(
                    "SELECT payload_json FROM config_assets WHERE asset_type=? AND scope=? AND tenant_id=? AND version=?",
                    (key.asset_type, key.scope, key.tenant_id, v),
                ).fetchone()
                if not row2:
                    return None
                return v, _json_loads(row2[0])
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_published_row(self, *, key: ConfigRegistryKey) -> Optional[Dict[str, Any]]:
        await self.init()

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(self._db_path)
            try:
                row = conn.execute(
                    """
                    SELECT asset_type, scope, tenant_id, channel, version, prev_version, updated_at, updated_by, note
                    FROM config_published
                    WHERE asset_type=? AND scope=? AND tenant_id=? AND channel=?;
                    """,
                    (key.asset_type, key.scope, key.tenant_id, key.channel),
                ).fetchone()
                if not row:
                    return None
                cols = ["asset_type", "scope", "tenant_id", "channel", "version", "prev_version", "updated_at", "updated_by", "note"]
                return {cols[i]: row[i] for i in range(len(cols))}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def list_versions(
        self,
        *,
        asset_type: str,
        scope: str,
        tenant_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        await self.init()
        limit = max(1, min(int(limit or 50), 200))
        offset = max(0, int(offset or 0))

        def _sync() -> Dict[str, Any]:
            conn = sqlite3.connect(self._db_path)
            try:
                rows = conn.execute(
                    """
                    SELECT version, created_at, created_by, note
                    FROM config_assets
                    WHERE asset_type=? AND scope=? AND tenant_id=?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?;
                    """,
                    (asset_type, scope, tenant_id, limit, offset),
                ).fetchall()
                items = []
                for r in rows:
                    items.append({"version": r[0], "created_at": r[1], "created_by": r[2], "note": r[3]})
                return {"items": items, "limit": limit, "offset": offset}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def get_asset(
        self,
        *,
        asset_type: str,
        scope: str,
        tenant_id: str,
        version: str,
    ) -> Optional[Dict[str, Any]]:
        await self.init()
        v = str(version or "").strip()
        if not v:
            return None

        def _sync() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(self._db_path)
            try:
                row = conn.execute(
                    """
                    SELECT payload_json, created_at, created_by, note
                    FROM config_assets
                    WHERE asset_type=? AND scope=? AND tenant_id=? AND version=?;
                    """,
                    (asset_type, scope, tenant_id, v),
                ).fetchone()
                if not row:
                    return None
                return {
                    "version": v,
                    "payload": _json_loads(row[0]),
                    "created_at": row[1],
                    "created_by": row[2],
                    "note": row[3],
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)


_registry_singleton: Optional[ConfigRegistryStore] = None


def get_config_registry_store(db_path: Optional[str] = None) -> ConfigRegistryStore:
    global _registry_singleton
    desired = db_path or os.environ.get("AIPLAT_EXECUTION_DB_PATH", "data/aiplat_executions.sqlite3")
    if _registry_singleton is None or getattr(_registry_singleton, "_db_path", None) != str(desired):
        _registry_singleton = ConfigRegistryStore(db_path=str(desired))
    return _registry_singleton
