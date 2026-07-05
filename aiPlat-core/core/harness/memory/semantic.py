import logging
"""
Semantic Memory

Long-term memory with vector-based storage.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .embedding import EmbeddingProvider, get_embedding_provider


@dataclass
class MemoryItem:
    """A stored memory item"""
    id: str
    content: str
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    accessed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = 0
    expires_at: Optional[datetime] = None       # 过期时间 (None = 永不过期)
    is_deleted: bool = False                     # 软删除标记


class SemanticMemory:
    """Semantic memory - long-term knowledge storage"""

    def __init__(self, store_type: str = "simple", tenant_id: str = "default"):
        self._store_type = store_type
        self._tenant_id = tenant_id or "default"
        self._items: Dict[str, MemoryItem] = {}
        if store_type == "sqlite":
            self._init_sqlite()

    def _init_sqlite(self) -> None:
        import sqlite3
        import os
        base = os.path.expanduser("~/.aiplat")
        tid = getattr(self, '_tenant_id', 'default') or 'default'
        if tid != "default":
            db_path = os.path.join(base, f"memory_semantic_{tid}.sqlite3")
        else:
            db_path = os.path.join(base, "memory_semantic.sqlite3")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS semantic_memories (
                key TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                metadata_json TEXT DEFAULT '{}',
                embedding BLOB,
                created_at TEXT,
                accessed_at TEXT,
                access_count INTEGER DEFAULT 0,
                expires_at TEXT,
                is_deleted INTEGER DEFAULT 0
            )
        """)
        # Migration: add new columns for existing DBs
        try:
            self._conn.execute("ALTER TABLE semantic_memories ADD COLUMN expires_at TEXT")
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        try:
            self._conn.execute("ALTER TABLE semantic_memories ADD COLUMN is_deleted INTEGER DEFAULT 0")
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        self._conn.commit()
        self._load_from_sqlite()

    def _load_from_sqlite(self) -> None:
        """Load existing memories from SQLite into the in-memory index."""
        if not hasattr(self, "_conn"):
            return
        for row in self._conn.execute(
            "SELECT key, content, metadata_json, embedding, access_count, expires_at, is_deleted "
            "FROM semantic_memories WHERE is_deleted = 0"
        ):
            import json
            emb = json.loads(row[3]) if row[3] else None
            meta = json.loads(row[2]) if row[2] else {}
            expires = datetime.fromisoformat(row[5]) if row[5] else None
            item = MemoryItem(
                id=row[0], content=row[1], embedding=emb, metadata=meta,
                access_count=row[4], expires_at=expires, is_deleted=bool(row[6]),
            )
            self._items[row[0]] = item

    async def store(
        self,
        key: str,
        content: str,
        metadata: Optional[Dict] = None,
        embedding: Optional[List[float]] = None,
        expires_at: Optional[datetime] = None,
    ) -> MemoryItem:
        """Store a memory item"""
        metadata = metadata or {}

        # Phase 23.1 G2: Semantic fact contradiction detection
        topic = metadata.get("topic", "")
        if topic and self._store_type == "sqlite":
            try:
                existing = self._find_by_topic(topic)
                if existing:
                    result = self._resolve_semantic_conflict(content, metadata, existing)
                    if result == "skip":
                        return None
                    elif result in ("overwrite", "downweight"):
                        self._decay_existing(existing[0], metadata)
            except Exception as e:
                logging.debug(str(e), exc_info=True)

        item = MemoryItem(
            id=key,
            content=content,
            embedding=embedding,
            metadata=metadata or {},
            expires_at=expires_at,
        )
        self._items[key] = item

        if self._store_type == "sqlite" and hasattr(self, "_conn"):
            import json
            emb_json = json.dumps(embedding) if embedding else None
            meta_json = json.dumps(metadata or {}, ensure_ascii=False)
            exp_str = expires_at.isoformat() if expires_at else None
            self._conn.execute(
                "INSERT OR REPLACE INTO semantic_memories(key, content, metadata_json, embedding, created_at, accessed_at, access_count, expires_at, is_deleted) VALUES(?,?,?,?,?,?,?,?,?)",
                (key, content, meta_json, emb_json, item.created_at.isoformat(), item.accessed_at.isoformat(), item.access_count, exp_str, int(item.is_deleted)),
            )
            self._conn.commit()
        return item
    
    async def retrieve(
        self,
        query: str,
        top_k: int = 3,
        threshold: float = 0.5,
        *,
        tenant_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> List[MemoryItem]:
        """Retrieve relevant memories using vector similarity (primary) or keyword match (fallback).
        On hit: dynamically renews expires_at to prevent high-frequency memories from being cleaned.
        Filters out soft-deleted items.
        """
        active_items = [item for item in self._items.values() if not item.is_deleted]
        # Defense-in-depth tenant+session isolation (§5.12): when a scope is given,
        # only items whose metadata matches are eligible — prevents cross-tenant recall.
        if tenant_id is not None or session_id is not None:
            active_items = [
                it for it in active_items
                if (tenant_id is None or (it.metadata or {}).get("tenant_id") == tenant_id)
                and (session_id is None or (it.metadata or {}).get("session_id") == session_id)
            ]
        vector_items = [(item, item.embedding) for item in active_items if item.embedding]

        if vector_items:
            try:
                from core.harness.memory.embedding import get_embedding_provider
                provider = get_embedding_provider()
                query_vec = await provider.embed_single(query)
                if query_vec:
                    scored = []
                    for item, emb in vector_items:
                        sim = EmbeddingProvider.cosine_similarity(query_vec, emb)
                        scored.append((item, sim))
                    scored.sort(key=lambda x: -x[1])
                    results = []
                    for item, sim in scored[:top_k]:
                        if sim >= threshold:
                            item.accessed_at = datetime.now(timezone.utc)
                            item.access_count += 1
                            self._renew_expiry(item)
                            results.append(item)
                    if results:
                        return results
            except Exception as e:
                logging.debug(str(e), exc_info=True)

        # Fallback: keyword matching
        results = []
        query_lower = query.lower()
        query_words = set(query_lower.split())

        for item in active_items:
            content_words = set(item.content.lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                item.accessed_at = datetime.now(timezone.utc)
                item.access_count += 1
                self._renew_expiry(item)
                results.append((item, overlap))

        results.sort(key=lambda x: x[1], reverse=True)
        return [item for item, score in results[:top_k] if score >= threshold]

    def _renew_expiry(self, item: MemoryItem) -> None:
        """Dynamically extend expiry on access — high-frequency memories live longer."""
        if item.expires_at is not None:
            new_expiry = datetime.now(timezone.utc).timestamp() + 7 * 86400
            item.expires_at = datetime.fromtimestamp(
                max(item.expires_at.timestamp(), new_expiry),
                tz=timezone.utc,
            )
            try:
                from core.harness.memory.metrics import inc_semantic_renewed
                inc_semantic_renewed()
            except Exception as e:
                logging.debug(str(e), exc_info=True)
    
    async def get(self, key: str, *, tenant_id: Optional[str] = None,
                  session_id: Optional[str] = None) -> Optional[MemoryItem]:
        """Get a specific memory. Filters soft-deleted items.

        When tenant_id/session_id are provided, enforces tenant+session isolation
        (returns None for cross-tenant/session keys) — defense-in-depth matching
        get_deleted()'s isolation guarantee (§5.12).
        """
        item = self._items.get(key)
        if item and not item.is_deleted:
            if tenant_id is not None or session_id is not None:
                meta = item.metadata or {}
                if (tenant_id is not None and meta.get("tenant_id") != tenant_id) or \
                   (session_id is not None and meta.get("session_id") != session_id):
                    return None
            self._renew_expiry(item)
            return item
        return None

    async def get_deleted(self, key: str, *, tenant_id: str, session_id: str) -> Optional[MemoryItem]:
        """Retrieve a soft-deleted memory (for recovery). Requires tenant+session isolation."""
        item = self._items.get(key)
        if item and item.is_deleted:
            # Enforce tenant + session isolation — caller cannot bypass
            meta = item.metadata or {}
            if meta.get("tenant_id") == tenant_id and meta.get("session_id") == session_id:
                return item
        return None

    async def recover_deleted(self, key: str) -> bool:
        """Restore a soft-deleted memory."""
        item = self._items.get(key)
        if item and item.is_deleted:
            item.is_deleted = False
            if self._store_type == "sqlite" and hasattr(self, "_conn"):
                self._conn.execute(
                    "UPDATE semantic_memories SET is_deleted=0 WHERE key=?", (key,)
                )
                self._conn.commit()
            return True
        return False

    async def delete(self, key: str) -> bool:
        """Soft-delete a memory (sets is_deleted=1)."""
        item = self._items.get(key)
        if item:
            item.is_deleted = True
            if self._store_type == "sqlite" and hasattr(self, "_conn"):
                self._conn.execute(
                    "UPDATE semantic_memories SET is_deleted=1 WHERE key=?", (key,)
                )
                self._conn.commit()
            return True
        return False

    async def hard_delete(self, key: str) -> bool:
        """Permanently remove a memory (use only for GDPR/compliance)."""
        if key in self._items:
            del self._items[key]
            if self._store_type == "sqlite" and hasattr(self, "_conn"):
                self._conn.execute("DELETE FROM semantic_memories WHERE key=?", (key,))
                self._conn.commit()
            return True
        return False

    async def cleanup_expired(self) -> int:
        """Soft-delete expired memories that have low access frequency.
        
        Cleanup condition (BOTH must be met):
          - expires_at < now()  (expired)
          - access_count < 3    (rarely accessed — not worth keeping)
        
        High-frequency memories are kept even if expired (dynamic renewal).
        Returns count of items soft-deleted.
        """
        now = datetime.now(timezone.utc)
        to_delete = []
        for key, item in list(self._items.items()):
            if item.is_deleted:
                continue
            if item.expires_at is not None and item.expires_at < now:
                if item.access_count < 3:
                    to_delete.append(key)

        for key in to_delete:
            await self.delete(key)
        if to_delete:
            try:
                from core.harness.memory.metrics import inc_semantic_expired
                for _ in to_delete:
                    inc_semantic_expired()
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        return len(to_delete)
    
    async def search_by_metadata(
        self,
        metadata_filter: Dict[str, Any]
    ) -> List[MemoryItem]:
        """Search by metadata fields (excludes soft-deleted)."""
        results = []
        for item in self._items.values():
            if item.is_deleted:
                continue
            match = True
            for key, value in metadata_filter.items():
                if item.metadata.get(key) != value:
                    match = False
                    break
            if match:
                results.append(item)
        return results

    def get_stats(self) -> Dict:
        """Get memory statistics"""
        active = sum(1 for item in self._items.values() if not item.is_deleted)
        deleted = sum(1 for item in self._items.values() if item.is_deleted)
        return {
            "total_items": len(self._items),
            "active_items": active,
            "deleted_items": deleted,
            "total_accesses": sum(item.access_count for item in self._items.values()),
            "avg_access_count": sum(item.access_count for item in self._items.values()) / max(1, len(self._items)),
        }

    # ── Phase 23.1 G2: Semantic conflict detection helpers ──

    def _find_by_topic(self, topic: str, limit: int = 3) -> list:
        """Query SQLite for existing entries with same topic tag."""
        import json as _json
        if not hasattr(self, "_conn"):
            return []
        rows = self._conn.execute(
            "SELECT key, content, metadata_json FROM semantic_memories "
            "WHERE json_extract(metadata_json, '$.topic') = ? "
            "AND is_deleted = 0 ORDER BY json_extract(metadata_json, '$.timestamp') DESC LIMIT ?",
            (topic, limit),
        ).fetchall()
        return [{"key": r[0], "content": r[1], "metadata": _json.loads(r[2] or "{}")} for r in rows]

    def _resolve_semantic_conflict(self, new_content: str, new_meta: dict,
                                    existing: list) -> str:
        """Conflict engine: overwrite/downweight/append/retain based on 5 dimensions."""
        old = existing[0]
        old_meta = old.get("metadata", old)

        # Dimension 1: version
        new_ver = self._parse_version(new_meta.get("version", "0"))
        old_ver = self._parse_version(old_meta.get("version", "0") if isinstance(old_meta, dict) else "0")
        # Dimension 2: timestamp
        new_ts = float(new_meta.get("timestamp", 0) or 0)
        old_ts = float(old_meta.get("timestamp", 0) or 0) if isinstance(old_meta, dict) else 0
        # Dimension 3: confidence
        new_conf = float(new_meta.get("confidence", 0.5) or 0.5)
        old_conf = float(old_meta.get("confidence", 0.5) or 0.5) if isinstance(old_meta, dict) else 0.5
        # Dimension 4: content similarity (Jaccard)
        old_content = old.get("content", "")
        sim = self._text_similarity(new_content, old_content)

        if new_ver > old_ver and new_ts > old_ts:
            return "overwrite"
        if new_conf > old_conf + 0.2 and sim > 0.7:
            return "overwrite"
        if new_conf > old_conf and sim > 0.5:
            return "downweight"
        if sim < 0.3:
            return "append"
        if new_ts > old_ts + 86400 * 30 and new_conf > 0.5:
            return "overwrite"
        return "retain"

    def _decay_existing(self, entry: dict, new_meta: dict) -> None:
        """Soft-delete old entry (preserves audit trail)."""
        if hasattr(self, "_conn"):
            self._conn.execute(
                "UPDATE semantic_memories SET is_deleted=1 WHERE key=?",
                (entry["key"],),
            )
            self._conn.commit()

    @staticmethod
    def _parse_version(v: str) -> int:
        """Parse semantic version string to comparable int (e.g. v2.0 → 20)."""
        try:
            parts = v.replace("v", "").split(".")
            return int(parts[0]) * 10 + int(parts[1]) if len(parts) >= 2 else int(parts[0]) * 10
        except (ValueError, IndexError, AttributeError):
            return 0

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """Jaccard similarity — zero dependency, fast for short texts."""
        if not a.strip() or not b.strip():
            return 0.0
        sa = set(a.lower().split())
        sb = set(b.lower().split())
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)


__all__ = ["SemanticMemory", "MemoryItem"]