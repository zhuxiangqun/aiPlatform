"""
import logging
LongTermMemoryMixin — extracted from ExecutionStore global_mixin.py.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
import anyio
import uuid
from ._base import _json_dumps, _json_loads


class LongTermMemoryMixin:
    """Extracted from ExecutionStore."""
    async def add_long_term_memory(self, *, user_id: str, content: str, key: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            now = time.time()
            meta = metadata or {}
            rec = {
                "id": f"ltm-{uuid.uuid4().hex[:12]}",
                "user_id": str(user_id or "system"),
                "key": str(key) if key is not None else None,
                "content": str(content or ""),
                "metadata_json": _json_dumps(meta),
                "created_at": now,
                "updated_at": now,
                "relevance_decay": 1.0,
                "source_tag": str(meta.get("source_tag", "") or ""),
                "trust_weight": float(meta.get("trust_weight", 1.0) or 1.0),
                "provenance": str(meta.get("provenance", "") or ""),
            }
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO long_term_memories("
                    "id,user_id,key,content,metadata_json,"
                    "created_at,updated_at,relevance_decay,"
                    "source_tag,trust_weight,provenance"
                    ") VALUES(?,?,?,?,?,?,?,?,?,?,?);",
                    (rec["id"], rec["user_id"], rec["key"], rec["content"], rec["metadata_json"],
                     rec["created_at"], rec["updated_at"], rec["relevance_decay"],
                     rec["source_tag"], rec["trust_weight"], rec["provenance"]),
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
            "source_tag": row.get("source_tag", ""),
            "trust_weight": row.get("trust_weight", 1.0),
            "provenance": row.get("provenance", ""),
            "relevance_decay": row.get("relevance_decay", 1.0),
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
                    "source_tag": r.get("source_tag", ""),
                    "trust_weight": r.get("trust_weight", 1.0),
                    "provenance": r.get("provenance", ""),
                    "relevance_decay": r.get("relevance_decay", 1.0),
                }
            )
        return out

    async def list_long_term_memories(self, *, user_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Phase 40: List all long-term memories for a user (paginated)."""
        return await self.list_long_term_memories_filtered(
            user_id=user_id, limit=limit, offset=offset,
        )

    async def list_long_term_memories_filtered(
        self, *, user_id: str, limit: int = 50, offset: int = 0,
        source_tag: Optional[str] = None,
        min_trust: Optional[float] = None,
        date_from: Optional[float] = None,
        date_to: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Phase 40: List long-term memories with structured filters (no raw SQL injection risk)."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> List[Dict[str, Any]]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                uid = str(user_id or "system")
                sql = "SELECT * FROM long_term_memories WHERE user_id = ?"
                params: list = [uid]
                if source_tag is not None:
                    sql += " AND source_tag = ?"
                    params.append(str(source_tag))
                if min_trust is not None:
                    sql += " AND trust_weight >= ?"
                    params.append(float(min_trust))
                if date_from is not None:
                    sql += " AND created_at >= ?"
                    params.append(float(date_from))
                if date_to is not None:
                    sql += " AND created_at <= ?"
                    params.append(float(date_to))
                sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
                params.extend([int(limit), int(offset)])
                rows = conn.execute(sql, tuple(params)).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

        rows = await anyio.to_thread.run_sync(_sync)
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({
                "id": r["id"], "user_id": r["user_id"],
                "key": r.get("key"), "content": r.get("content"),
                "metadata": _json_loads(r.get("metadata_json")) or {},
                "created_at": r.get("created_at"),
                "source_tag": r.get("source_tag", ""),
                "trust_weight": r.get("trust_weight", 1.0),
                "provenance": r.get("provenance", ""),
                "relevance_decay": r.get("relevance_decay", 1.0),
            })
        return out

    async def update_long_term_memory(self, *, memory_id: str, content: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None, key: Optional[str] = None) -> Dict[str, Any]:
        """Phase 40: Update a long-term memory entry."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                now = time.time()
                existing = conn.execute(
                    "SELECT * FROM long_term_memories WHERE id = ?", (memory_id,)
                ).fetchone()
                if not existing:
                    raise ValueError(f"Memory {memory_id} not found")
                new_content = content if content is not None else existing["content"]
                new_key = key if key is not None else existing["key"]
                meta = dict(_json_loads(existing["metadata_json"]) or {})
                if metadata:
                    meta.update(metadata)
                new_meta = _json_dumps(meta)
                conn.execute(
                    "UPDATE long_term_memories SET content=?, key=?, metadata_json=?, updated_at=? WHERE id=?",
                    (new_content, new_key, new_meta, now, memory_id),
                )
                try:
                    conn.execute(
                        "UPDATE long_term_memories_fts SET content=?, key=? WHERE id=?",
                        (new_content, new_key, memory_id),
                    )
                except Exception:
                    logging.getLogger(__name__).debug('_sync failed', exc_info=True)
                conn.commit()
                return dict(existing) | {"content": new_content, "key": new_key}
            finally:
                conn.close()

        row = await anyio.to_thread.run_sync(_sync)
        return {
            "id": row["id"], "user_id": row["user_id"],
            "key": row.get("key"), "content": row.get("content"),
            "metadata": _json_loads(row.get("metadata_json")) or {},
            "created_at": row.get("created_at"),
            "source_tag": row.get("source_tag", ""),
            "trust_weight": row.get("trust_weight", 1.0),
            "provenance": row.get("provenance", ""),
            "relevance_decay": row.get("relevance_decay", 1.0),
        }

    async def delete_long_term_memory(self, *, memory_id: str) -> bool:
        """Phase 40: Delete a long-term memory entry."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> bool:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    "DELETE FROM long_term_memories WHERE id = ?", (memory_id,)
                )
                try:
                    conn.execute("DELETE FROM long_term_memories_fts WHERE id = ?", (memory_id,))
                except Exception:
                    logging.getLogger(__name__).debug('_sync failed', exc_info=True)
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

        return await anyio.to_thread.run_sync(_sync)

