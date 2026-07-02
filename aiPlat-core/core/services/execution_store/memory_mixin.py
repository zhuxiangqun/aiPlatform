"""
MemoryMixin — extracted from ExecutionStore events_mixin.py.

Auto-generated via Mixin split. Contains entity-specific CRUD methods.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
from ._base import _json_dumps, _json_loads


class MemoryMixin:
    """Extracted from ExecutionStore."""
    # ==================== Enterprise Memory Pins / Blocks (PR-09) ====================

    async def pin_memory_message(
        self,
        *,
        tenant_id: Optional[str],
        session_id: str,
        message_id: str,
        created_by: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = float(time.time())
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO memory_pins(tenant_id, session_id, message_id, created_by, note, created_at)
                    VALUES(?, ?, ?, ?, ?, ?)
                    ON CONFLICT(tenant_id, message_id) DO UPDATE SET
                      session_id=excluded.session_id,
                      created_by=excluded.created_by,
                      note=excluded.note,
                      created_at=excluded.created_at;
                    """,
                    (
                        str(tenant_id or ""),
                        str(session_id),
                        str(message_id),
                        str(created_by) if created_by else None,
                        str(note) if note else None,
                        now,
                    ),
                )
                conn.commit()
                return {
                    "tenant_id": str(tenant_id or ""),
                    "session_id": str(session_id),
                    "message_id": str(message_id),
                    "created_by": str(created_by) if created_by else None,
                    "note": str(note) if note else None,
                    "created_at": now,
                }
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

    async def unpin_memory_message(self, *, tenant_id: Optional[str], message_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM memory_pins WHERE tenant_id=? AND message_id=?",
                    (str(tenant_id or ""), str(message_id)),
                )
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return bool(await anyio.to_thread.run_sync(_sync))

    async def list_memory_pins(
        self, *, tenant_id: Optional[str], session_id: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                clauses = ["tenant_id=?"]
                params: List[Any] = [str(tenant_id or "")]
                if session_id:
                    clauses.append("session_id=?")
                    params.append(str(session_id))
                where = "WHERE " + " AND ".join(clauses)
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM memory_pins {where};", tuple(params)).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT * FROM memory_pins {where} ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                    tuple(params + [int(limit), int(offset)]),
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total, "limit": int(limit), "offset": int(offset)}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

