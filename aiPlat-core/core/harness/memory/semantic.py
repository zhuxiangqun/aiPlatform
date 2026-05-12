"""
Semantic Memory

Long-term memory with vector-based storage.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

from .embedding import EmbeddingProvider, get_embedding_provider


@dataclass
class MemoryItem:
    """A stored memory item"""
    id: str
    content: str
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    accessed_at: datetime = field(default_factory=datetime.utcnow)
    access_count: int = 0


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
                access_count INTEGER DEFAULT 0
            )
        """)
        self._conn.commit()
        self._load_from_sqlite()

    def _load_from_sqlite(self) -> None:
        """Load existing memories from SQLite into the in-memory index."""
        if not hasattr(self, "_conn"):
            return
        for row in self._conn.execute("SELECT key, content, metadata_json, embedding, access_count FROM semantic_memories"):
            import json
            emb = json.loads(row[3]) if row[3] else None
            meta = json.loads(row[2]) if row[2] else {}
            item = MemoryItem(id=row[0], content=row[1], embedding=emb, metadata=meta, access_count=row[4])
            self._items[row[0]] = item

    async def store(
        self,
        key: str,
        content: str,
        metadata: Optional[Dict] = None,
        embedding: Optional[List[float]] = None
    ) -> MemoryItem:
        """Store a memory item"""
        item = MemoryItem(
            id=key,
            content=content,
            embedding=embedding,
            metadata=metadata or {}
        )
        self._items[key] = item

        if self._store_type == "sqlite" and hasattr(self, "_conn"):
            import json
            emb_json = json.dumps(embedding) if embedding else None
            meta_json = json.dumps(metadata or {}, ensure_ascii=False)
            self._conn.execute(
                "INSERT OR REPLACE INTO semantic_memories(key, content, metadata_json, embedding, created_at, accessed_at, access_count) VALUES(?,?,?,?,?,?,?)",
                (key, content, meta_json, emb_json, item.created_at.isoformat(), item.accessed_at.isoformat(), item.access_count),
            )
            self._conn.commit()
        return item
    
    async def retrieve(
        self,
        query: str,
        top_k: int = 3,
        threshold: float = 0.5
    ) -> List[MemoryItem]:
        """Retrieve relevant memories using vector similarity (primary) or keyword match (fallback)."""
        vector_items = [(item, item.embedding) for item in self._items.values() if item.embedding]

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
                            item.accessed_at = datetime.utcnow()
                            item.access_count += 1
                            results.append(item)
                    if results:
                        return results
            except Exception:
                pass

        # Fallback: keyword matching
        results = []
        query_lower = query.lower()
        query_words = set(query_lower.split())

        for item in self._items.values():
            content_words = set(item.content.lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                item.accessed_at = datetime.utcnow()
                item.access_count += 1
                results.append((item, overlap))

        results.sort(key=lambda x: x[1], reverse=True)
        return [item for item, score in results[:top_k] if score >= threshold]
    
    async def get(self, key: str) -> Optional[MemoryItem]:
        """Get a specific memory"""
        return self._items.get(key)
    
    async def delete(self, key: str) -> bool:
        """Delete a memory"""
        if key in self._items:
            del self._items[key]
            if self._store_type == "sqlite" and hasattr(self, "_conn"):
                self._conn.execute("DELETE FROM semantic_memories WHERE key=?", (key,))
                self._conn.commit()
            return True
        return False
    
    async def search_by_metadata(
        self,
        metadata_filter: Dict[str, Any]
    ) -> List[MemoryItem]:
        """Search by metadata fields"""
        results = []
        for item in self._items.values():
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
        return {
            "total_items": len(self._items),
            "total_accesses": sum(item.access_count for item in self._items.values()),
            "avg_access_count": sum(item.access_count for item in self._items.values()) / max(1, len(self._items))
        }


__all__ = ["SemanticMemory", "MemoryItem"]