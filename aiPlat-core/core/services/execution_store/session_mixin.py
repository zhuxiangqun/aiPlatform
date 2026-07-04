"""
SessionMixin — extracted from ExecutionStore global_mixin.py.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
import anyio
import uuid
from ._base import _json_dumps, _json_loads


class SessionMixin:
    """Extracted from ExecutionStore."""
    async def create_memory_session(
        self,
        *,
        tenant_id: Optional[str] = None,
        user_id: str,
        agent_type: str = "default",
        session_type: str = "session",
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            sid = str(session_id) if session_id else f"sess-{uuid.uuid4().hex[:10]}"
            rec = {
                "id": sid,
                "tenant_id": str(tenant_id) if tenant_id is not None else None,
                "user_id": str(user_id or "system"),
                "agent_type": str(agent_type or "default"),
                "session_type": str(session_type or "session"),
                "status": "active",
                "metadata_json": _json_dumps(metadata or {}),
                "message_count": 0,
                "created_at": now,
                "updated_at": now,
            }
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO memory_sessions(id,tenant_id,user_id,agent_type,session_type,status,metadata_json,message_count,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET
                      tenant_id=excluded.tenant_id,
                      user_id=excluded.user_id,
                      agent_type=excluded.agent_type,
                      session_type=excluded.session_type,
                      status=excluded.status,
                      metadata_json=excluded.metadata_json,
                      updated_at=excluded.updated_at;
                    """,
                    (
                        rec["id"],
                        rec["tenant_id"],
                        rec["user_id"],
                        rec["agent_type"],
                        rec["session_type"],
                        rec["status"],
                        rec["metadata_json"],
                        rec["message_count"],
                        rec["created_at"],
                        rec["updated_at"],
                    ),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {**row, "metadata": _json_loads(row.get("metadata_json")) or {}}

    async def add_memory_message(
        self,
        *,
        tenant_id: Optional[str] = None,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
        sensitivity: Optional[str] = None,
        source_run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            mid = f"msg-{uuid.uuid4().hex[:12]}"
            rec = {
                "id": mid,
                "session_id": str(session_id or "default"),
                "tenant_id": str(tenant_id) if tenant_id is not None else None,
                "user_id": str(user_id or "system"),
                "role": str(role or "user"),
                "content": str(content or ""),
                "sensitivity": str(sensitivity) if sensitivity is not None else None,
                "source_run_id": str(source_run_id) if source_run_id is not None else None,
                "metadata_json": _json_dumps(metadata or {}),
                "trace_id": str(trace_id) if trace_id else None,
                "run_id": str(run_id) if run_id else None,
                "created_at": now,
            }
            conn = self._connect()
            try:
                # Ensure session exists (idempotent).
                conn.execute(
                    """
                    INSERT INTO memory_sessions(id,tenant_id,user_id,agent_type,session_type,status,metadata_json,message_count,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at;
                    """,
                    (
                        rec["session_id"],
                        rec["tenant_id"],
                        rec["user_id"],
                        "default",
                        "session",
                        "active",
                        "{}",
                        0,
                        now,
                        now,
                    ),
                )
                # Insert message with v32 columns; fallback to legacy insert for compatibility.
                try:
                    conn.execute(
                        """
                        INSERT INTO memory_messages(
                          id,session_id,tenant_id,user_id,role,content,sensitivity,source_run_id,metadata_json,trace_id,run_id,created_at
                        )
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?);
                        """,
                        (
                            rec["id"],
                            rec["session_id"],
                            rec["tenant_id"],
                            rec["user_id"],
                            rec["role"],
                            rec["content"],
                            rec["sensitivity"],
                            rec["source_run_id"],
                            rec["metadata_json"],
                            rec["trace_id"],
                            rec["run_id"],
                            rec["created_at"],
                        ),
                    )
                except Exception:
                    conn.execute(
                        """
                        INSERT INTO memory_messages(id,session_id,user_id,role,content,metadata_json,trace_id,run_id,created_at)
                        VALUES(?,?,?,?,?,?,?,?,?);
                        """,
                        (
                            rec["id"],
                            rec["session_id"],
                            rec["user_id"],
                            rec["role"],
                            rec["content"],
                            rec["metadata_json"],
                            rec["trace_id"],
                            rec["run_id"],
                            rec["created_at"],
                        ),
                    )
                # best-effort: sync FTS
                try:
                    conn.execute(
                        "INSERT INTO memory_messages_fts(id,user_id,session_id,role,content) VALUES(?,?,?,?,?);",
                        (rec["id"], rec["user_id"], rec["session_id"], rec["role"], rec["content"]),
                    )
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
                conn.execute(
                    "UPDATE memory_sessions SET message_count = message_count + 1, updated_at = ? WHERE id = ?;",
                    (now, rec["session_id"]),
                )
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {**row, "metadata": _json_loads(row.get("metadata_json")) or {}}

    async def list_memory_sessions(
        self, *, tenant_id: Optional[str] = None, user_id: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                where = ""
                args: List[Any] = []
                if tenant_id is not None:
                    where = "WHERE tenant_id = ?"
                    args.append(str(tenant_id))
                if user_id:
                    if where:
                        where += " AND user_id = ?"
                    else:
                        where = "WHERE user_id = ?"
                    args.append(str(user_id))
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM memory_sessions {where};", args).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"SELECT * FROM memory_sessions {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?;",
                    [*args, int(limit), int(offset)],
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items = []
        for r in res.get("items") or []:
            items.append({**r, "metadata": _json_loads(r.get("metadata_json")) or {}})
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    async def get_memory_session(self, *, session_id: str) -> Optional[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Optional[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute("SELECT * FROM memory_sessions WHERE id = ?;", (str(session_id),)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        if not row:
            return None
        return {**row, "metadata": _json_loads(row.get("metadata_json")) or {}}

    async def delete_memory_session(self, *, session_id: str) -> bool:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM memory_sessions WHERE id = ?;", (str(session_id),))
                conn.execute("DELETE FROM memory_messages WHERE session_id = ?;", (str(session_id),))
                try:
                    conn.execute("DELETE FROM memory_messages_fts WHERE session_id = ?;", (str(session_id),))
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
                conn.commit()
                return bool(cur.rowcount)
            finally:
                conn.close()

        return bool(await anyio.to_thread.run_sync(_sync))

    async def list_memory_messages(
        self, *, session_id: str, tenant_id: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                total_row = conn.execute(
                    "SELECT COUNT(1) AS c FROM memory_messages WHERE session_id = ? AND (? IS NULL OR tenant_id = ?);",
                    (
                        str(session_id),
                        str(tenant_id) if tenant_id is not None else None,
                        str(tenant_id) if tenant_id is not None else None,
                    ),
                ).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    """
                    SELECT * FROM memory_messages
                    WHERE session_id = ?
                      AND (? IS NULL OR tenant_id = ?)
                    ORDER BY created_at ASC
                    LIMIT ? OFFSET ?;
                    """,
                    (
                        str(session_id),
                        str(tenant_id) if tenant_id is not None else None,
                        str(tenant_id) if tenant_id is not None else None,
                        int(limit),
                        int(offset),
                    ),
                ).fetchall()
                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        res = await anyio.to_thread.run_sync(_sync)
        items = []
        for r in res.get("items") or []:
            items.append({**r, "metadata": _json_loads(r.get("metadata_json")) or {}})
        return {"items": items, "total": int(res.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    async def search_memory_messages(
        self,
        *,
        query: str,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                uid = str(user_id) if user_id else None
                tid = str(tenant_id) if tenant_id is not None else None
                q = str(query or "").strip()
                # Prefer FTS when available; fallback to LIKE.
                try:
                    if q:
                        q_fts = q.replace('"', '""')
                        where_uid = "AND user_id = ?" if uid else ""
                        params: List[Any] = [q_fts]
                        if uid:
                            params.append(uid)
                        params.extend([int(limit), int(offset)])
                        rows = conn.execute(
                            f"""
                            SELECT * FROM memory_messages_fts
                            WHERE memory_messages_fts MATCH ?
                              {where_uid}
                            LIMIT ? OFFSET ?;
                            """,
                            params,
                        ).fetchall()
                        # FTS table doesn't have tenant_id; filter via memory_messages join (best-effort).
                        ids = [str(r["id"]) for r in rows if r and r["id"]]
                        if not ids:
                            return {"items": [], "total": 0}
                        placeholders = ",".join(["?"] * len(ids))
                        args2: List[Any] = list(ids)
                        where2 = f"WHERE id IN ({placeholders})"
                        if tid is not None:
                            where2 += " AND tenant_id = ?"
                            args2.append(tid)
                        rows2 = conn.execute(
                            f"SELECT id,user_id,session_id,role,content,tenant_id,run_id,source_run_id,sensitivity FROM memory_messages {where2};",
                            tuple(args2),
                        ).fetchall()
                        items = []
                        for r2 in rows2:
                            items.append(
                                {
                                    "id": r2["id"],
                                    "user_id": r2["user_id"],
                                    "session_id": r2["session_id"],
                                    "role": r2["role"],
                                    "content": str(r2["content"] or "")[:200],
                                    "tenant_id": r2["tenant_id"] if "tenant_id" in r2.keys() else None,
                                    "run_id": r2["run_id"] if "run_id" in r2.keys() else None,
                                    "source_run_id": r2["source_run_id"] if "source_run_id" in r2.keys() else None,
                                    "sensitivity": r2["sensitivity"] if "sensitivity" in r2.keys() else None,
                                    "score": 1.0,
                                }
                            )
                        return {"items": items, "total": len(items)}
                except Exception as e:
                    logging.debug(str(e), exc_info=True)

                if not q:
                    return {"items": [], "total": 0}
                like = f"%{q}%"
                where_parts = ["content LIKE ?"]
                params2: List[Any] = [like]
                if uid:
                    where_parts.append("user_id = ?")
                    params2.append(uid)
                if tid is not None:
                    where_parts.append("tenant_id = ?")
                    params2.append(tid)
                where = "WHERE " + " AND ".join(where_parts)
                total_row = conn.execute(f"SELECT COUNT(1) AS c FROM memory_messages {where};", params2).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"""
                    SELECT id,user_id,session_id,role,content FROM memory_messages
                    {where}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?;
                    """,
                    [*params2, int(limit), int(offset)],
                ).fetchall()
                items = []
                for r in rows:
                    items.append(
                        {
                            "id": r["id"],
                            "user_id": r["user_id"],
                            "session_id": r["session_id"],
                            "role": r["role"],
                            "content": str(r["content"] or "")[:200],
                            "score": 1.0,
                        }
                    )
                return {"items": items, "total": total}
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

