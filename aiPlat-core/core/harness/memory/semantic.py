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

    def __init__(self, store_type: str = "simple"):
        self._store_type = store_type
        self._items: Dict[str, MemoryItem] = {}
        if store_type == "sqlite":
            self._init_sqlite()

    def _init_sqlite(self) -> None:
        import sqlite3
        import os
        db_path = os.path.expanduser("~/.aiplat/memory_semantic.sqlite3")
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


__all__ = ["SemanticMemory", "MemoryItem"]