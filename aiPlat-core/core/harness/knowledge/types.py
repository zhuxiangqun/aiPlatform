"""
Knowledge Types Module

Defines types for the knowledge system.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class KnowledgeType(Enum):
    """Knowledge types"""
    DOCUMENT = "document"
    CODE = "code"
    API = "api"
    CONCEPT = "concept"
    PROCEDURE = "procedure"
    FACT = "fact"
    RELATION = "relation"
    METADATA = "metadata"


class KnowledgeSource(Enum):
    """Knowledge sources"""
    FILE = "file"
    DATABASE = "database"
    API = "api"
    WEB = "web"
    USER = "user"
    SYSTEM = "system"


class KnowledgeStatus(Enum):
    """Knowledge status"""
    ACTIVE = "active"
    ARCHIVED = "archived"
    DEPRECATED = "deprecated"
    PENDING = "pending"


@dataclass
class KnowledgeMetadata:
    """Knowledge metadata"""
    source: KnowledgeSource
    author: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    version: str = "1.0.0"
    tags: List[str] = field(default_factory=list)
    confidence: float = 1.0
    relevance: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source.value,
            "author": self.author,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "version": self.version,
            "tags": self.tags,
            "confidence": self.confidence,
            "relevance": self.relevance,
        }


@dataclass
class KnowledgeEntry:
    """Knowledge entry"""
    id: str
    type: KnowledgeType
    content: str
    title: Optional[str] = None
    summary: Optional[str] = None
    embedding: Optional[List[float]] = None
    metadata: KnowledgeMetadata = field(default_factory=lambda: KnowledgeMetadata(source=KnowledgeSource.SYSTEM))
    status: KnowledgeStatus = KnowledgeStatus.ACTIVE
    references: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "content": self.content,
            "title": self.title,
            "summary": self.summary,
            "metadata": self.metadata.to_dict(),
            "status": self.status.value,
            "references": self.references,
        }


@dataclass
class KnowledgeQuery:
    """Knowledge query"""
    query: str
    query_embedding: Optional[List[float]] = None
    types: Optional[List[KnowledgeType]] = None
    sources: Optional[List[KnowledgeSource]] = None
    tags: Optional[List[str]] = None
    limit: int = 10
    min_confidence: float = 0.0
    min_relevance: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "types": [t.value for t in self.types] if self.types else None,
            "sources": [s.value for s in self.sources] if self.sources else None,
            "tags": self.tags,
            "limit": self.limit,
            "min_confidence": self.min_confidence,
            "min_relevance": self.min_relevance,
        }


@dataclass
class KnowledgeResult:
    """Knowledge retrieval result"""
    entry: KnowledgeEntry
    score: float
    highlight: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry": self.entry.to_dict(),
            "score": self.score,
            "highlight": self.highlight,
        }


__all__ = [
    "KnowledgeType",
    "KnowledgeSource",
    "KnowledgeStatus",
    "KnowledgeMetadata",
    "KnowledgeEntry",
    "KnowledgeQuery",
    "KnowledgeResult",
]