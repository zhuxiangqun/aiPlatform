"""
Knowledge System Module

Provides knowledge management: types, retrieval.
"""

from .types import (
    KnowledgeType,
    KnowledgeSource,
    KnowledgeStatus,
    KnowledgeMetadata,
    KnowledgeEntry,
    KnowledgeQuery,
    KnowledgeResult,
)

from .retriever import (
    IRetriever,
    IEmbedder,
    HashEmbedder,
    InfraEmbedder,
    SimpleEmbedder,
    InMemoryRetriever,
    KnowledgeRetriever,
    create_retriever,
)

__all__ = [
    "KnowledgeType",
    "KnowledgeSource",
    "KnowledgeStatus",
    "KnowledgeMetadata",
    "KnowledgeEntry",
    "KnowledgeQuery",
    "KnowledgeResult",
    "IRetriever",
    "IEmbedder",
    "HashEmbedder",
    "InfraEmbedder",
    "SimpleEmbedder",
    "InMemoryRetriever",
    "KnowledgeRetriever",
    "create_retriever",
]
