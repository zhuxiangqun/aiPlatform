"""
Semantic Memory

Long-term memory with vector-based storage.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime


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
        return item
    
    async def retrieve(
        self,
        query: str,
        top_k: int = 3,
        threshold: float = 0.5
    ) -> List[MemoryItem]:
        """Retrieve relevant memories"""
        # In real implementation, this would use vector similarity
        # For now, simple keyword matching
        results = []
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        for item in self._items.values():
            # Simple relevance score
            content_words = set(item.content.lower().split())
            overlap = len(query_words & content_words)
            
            if overlap > 0:
                item.accessed_at = datetime.utcnow()
                item.access_count += 1
                results.append((item, overlap))
        
        # Sort by relevance
        results.sort(key=lambda x: x[1], reverse=True)
        
        # Return top K above threshold
        return [item for item, score in results[:top_k] if score >= threshold]
    
    async def get(self, key: str) -> Optional[MemoryItem]:
        """Get a specific memory"""
        return self._items.get(key)
    
    async def delete(self, key: str) -> bool:
        """Delete a memory"""
        if key in self._items:
            del self._items[key]
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