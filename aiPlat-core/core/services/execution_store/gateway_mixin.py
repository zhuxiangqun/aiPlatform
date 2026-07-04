"""
GatewayMixin — extracted from ExecutionStore.

Auto-generated via Mixin split from events_mixin.py.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
import anyio
import uuid
from ._base import _json_dumps, _json_loads


class GatewayMixin:
    """Extracted from ExecutionStore."""
    # ==================== Gateway Pairings / Tokens (Roadmap-3) ====================

    async def upsert_gateway_pairing(
        self,
        *,
        channel: str,
        channel_user_id: str,
        user_id: str,
        session_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            rec = {
                "id": f"gwp-{uuid.uuid4().hex[:12]}",
                "channel": str(channel or "default"),
                "channel_user_id": str(channel_user_id),
                "user_id": str(user_id or "system"),
                "session_id": str(session_id) if session_id else None,
                "tenant_id": str(tenant_id) if tenant_id else None,
                "metadata_json": _json_dumps(metadata or {}),
                "created_at": now,
                "updated_at": now,
            }
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                conn.execute(
                    """
                    INSERT INTO gateway_pairings(
                      id, channel, channel_user_id, user_id, session_id, tenant_id, metadata_json, created_at, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(channel, channel_user_id) DO UPDATE SET
                      user_id=excluded.user_id,
                      session_id=excluded.session_id,
                      tenant_id=excluded.tenant_id,
                      metadata_json=excluded.metadata_json,
                      updated_at=excluded.updated_at;
                    """,
                    (
                        rec["id"],
                        rec["channel"],
                        rec["channel_user_id"],
                        rec["user_id"],
                        rec["session_id"],
                        rec["tenant_id"],
                        rec["metadata_json"],
                        rec["created_at"],
                        rec["updated_at"],
                    ),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM gateway_pairings WHERE channel=? AND channel_user_id=?;",
                    (rec["channel"], rec["channel_user_id"]),
                ).fetchone()
                return dict(row) if row else rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {**row, "metadata": _json_loads(row.get("metadata_json")) or {}}

    async def resolve_gateway_pairing(self, *, channel: str, channel_user_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM gateway_pairings WHERE channel=? AND channel_user_id=?;",
                    (str(channel or "default"), str(channel_user_id)),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {**row, "metadata": _json_loads(row.get("metadata_json")) or {}}

    async def list_gateway_pairings(
        self,
        *,
        channel: Optional[str] = None,
        user_id: Optional[str] = None,
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
                if channel:
                    clauses.append("channel=?")
                    params.append(str(channel))
                if user_id:
                    clauses.append("user_id=?")
                    params.append(str(user_id))
                where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM gateway_pairings {where};", params).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT * FROM gateway_pairings {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?;",
                    [*params, int(limit), int(offset)],
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items = []
        for r in res.get("items") or []:
            items.append({**r, "metadata": _json_loads(r.get("metadata_json")) or {}})
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    async def delete_gateway_pairing(self, *, channel: str, channel_user_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM gateway_pairings WHERE channel=? AND channel_user_id=?;",
                    (str(channel or "default"), str(channel_user_id)),
                )
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return bool(await anyio.to_thread.run_sync(_sync))

    async def create_gateway_token(
        self,
        *,
        name: str,
        token: str,
        tenant_id: Optional[str] = None,
        enabled: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path
        import hashlib

        def _sync() -> Dict[str, Any]:
            now = time.time()
            rec = {
                "id": f"gwt-{uuid.uuid4().hex[:12]}",
                "name": str(name or "token"),
                "token_sha256": hashlib.sha256(str(token).encode("utf-8")).hexdigest(),
                "tenant_id": str(tenant_id) if tenant_id else None,
                "enabled": 1 if enabled else 0,
                "created_at": now,
                "metadata_json": _json_dumps(metadata or {}),
            }
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                conn.execute(
                    """
                    INSERT INTO gateway_tokens(id,name,token_sha256,tenant_id,enabled,created_at,metadata_json)
                    VALUES(?,?,?,?,?,?,?);
                    """,
                    (
                        rec["id"],
                        rec["name"],
                        rec["token_sha256"],
                        rec["tenant_id"],
                        rec["enabled"],
                        rec["created_at"],
                        rec["metadata_json"],
                    ),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {**row, "metadata": _json_loads(row.get("metadata_json")) or {}}

    async def validate_gateway_token(self, *, token: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path
        import hashlib

        def _sync() -> Optional[Dict[str, Any]]:
            sha = hashlib.sha256(str(token).encode("utf-8")).hexdigest()
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT * FROM gateway_tokens WHERE enabled=1 AND token_sha256=? ORDER BY created_at DESC LIMIT 1;",
                    (sha,),
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {**row, "metadata": _json_loads(row.get("metadata_json")) or {}}

    async def list_gateway_tokens(self, *, limit: int = 100, offset: int = 0, enabled: Optional[bool] = None) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                clauses = []
                params: List[Any] = []
                if enabled is not None:
                    clauses.append("enabled = ?")
                    params.append(1 if enabled else 0)
                where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM gateway_tokens {where};", params).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT * FROM gateway_tokens {where} ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                    [*params, int(limit), int(offset)],
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items = []
        for r in res.get("items") or []:
            # Never return token_sha256 to callers by default.
            rr = dict(r)
            rr.pop("token_sha256", None)
            items.append({**rr, "metadata": _json_loads(r.get("metadata_json")) or {}})
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    async def delete_gateway_token(self, *, token_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM gateway_tokens WHERE id=?;", (str(token_id),))
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return bool(await anyio.to_thread.run_sync(_sync))

    """Gateway pairing & token CRUD."""
    pass
