"""
LongTermMemoryMixin — extracted from ExecutionStore global_mixin.py.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
from ._base import _json_dumps, _json_loads


class LongTermMemoryMixin:
    """Extracted from ExecutionStore."""
    async def add_long_term_memory(self, *, user_id: str, content: str, key: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            rec = {
                "id": f"ltm-{uuid.uuid4().hex[:12]}",
                "user_id": str(user_id or "system"),
                "key": str(key) if key is not None else None,
                "content": str(content or ""),
                "metadata_json": _json_dumps(metadata or {}),
                "created_at": now,
                "updated_at": now,
                "relevance_decay": 1.0,
            }
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO long_term_memories(id,user_id,key,content,metadata_json,created_at,updated_at,relevance_decay) VALUES(?,?,?,?,?,?,?,?);",
                    (rec["id"], rec["user_id"], rec["key"], rec["content"], rec["metadata_json"], rec["created_at"], rec["updated_at"], rec["relevance_decay"]),
                )
                # Best-effort: keep FTS in sync if available.
                try:
                    conn.execute(
                        "INSERT INTO long_term_memories_fts(id,user_id,key,content) VALUES(?,?,?,?);",
                        (rec["id"], rec["user_id"], rec["key"], rec["content"]),
                    )
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
                conn.commit()
                return rec
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "key": row.get("key"),
            "content": row.get("content"),
            "metadata": _json_loads(row.get("metadata_json")) or {},
            "created_at": row.get("created_at"),
        }

    async def search_long_term_memory(self, *, user_id: str, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> List[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                uid = str(user_id or "system")
                import time as _time
                now = _time.time()
                # Decay constant: half-life ~60 days (lambda = ln(2)/60 ≈ 0.0116)
                decay_lambda = 0.0116

                # Prefer FTS when available; fallback to LIKE.
                try:
                    q_fts = str(query or "").replace('"', '""').strip()
                    if q_fts:
                        rows = conn.execute(
                            """
                            SELECT m.*,
                                   (m.relevance_decay * exp(? * (m.created_at - ?))) AS decayed_score
                            FROM long_term_memories m
                            JOIN (
                              SELECT id FROM long_term_memories_fts
                              WHERE long_term_memories_fts MATCH ?
                                AND user_id = ?
                              LIMIT ?
                            ) f ON f.id = m.id
                            ORDER BY decayed_score DESC;
                            """,
                            (decay_lambda, now, q_fts, uid, int(limit)),
                        ).fetchall()
                        return [dict(r) for r in rows]
                except Exception as e:
                    logging.debug(str(e), exc_info=True)

                q = f"%{query}%"
                rows = conn.execute(
                    """
                    SELECT *, (relevance_decay * exp(? * (created_at - ?))) AS decayed_score
                    FROM long_term_memories
                    WHERE user_id = ? AND (content LIKE ? OR key LIKE ?)
                    ORDER BY decayed_score DESC
                    LIMIT ?;
                    """,
                    (decay_lambda, now, uid, q, q, int(limit)),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

        rows = await anyio.to_thread.run_sync(_sync)
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "key": r.get("key"),
                    "content": r.get("content"),
                    "metadata": _json_loads(r.get("metadata_json")) or {},
                    "created_at": r.get("created_at"),
                }
            )
        return out

