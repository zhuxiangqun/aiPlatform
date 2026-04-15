"""
Knowledge System Module

Provides knowledge management: types, retrieval, indexing, and evolution.
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
    SimpleEmbedder,
    InMemoryRetriever,
    KnowledgeRetriever,
    create_retriever,
)

from .indexer import (
    IndexType,
    IndexConfig,
    KeywordExtractor,
    TextChunker,
    KnowledgeIndexer,
    create_indexer,
)

from .evolution import (
    EvolutionType,
    EvolutionStatus,
    EvolutionTrigger,
    EvolutionRecord,
    KnowledgeEvolution,
    create_evolution,
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
    "SimpleEmbedder",
    "InMemoryRetriever",
    "KnowledgeRetriever",
    "create_retriever",
    "IndexType",
    "IndexConfig",
    "KeywordExtractor",
    "TextChunker",
    "KnowledgeIndexer",
    "create_indexer",
    "EvolutionType",
    "EvolutionStatus",
    "EvolutionTrigger",
    "EvolutionRecord",
    "KnowledgeEvolution",
    "create_evolution",
]