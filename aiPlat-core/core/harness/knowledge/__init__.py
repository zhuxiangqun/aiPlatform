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
    SimpleEmbedder,
    InMemoryRetriever,
    VectorStoreRetriever,
    KnowledgeRetriever,
    create_retriever,
    create_vector_retriever,
)

from .sqlite_retriever import (
    SqliteEmbeddingRetriever,
    create_sqlite_retriever,
)

from .embedder import (
    SemanticEmbedder,
    create_default_embedder,
)

from .utils import (
    extract_keywords,
    score_text,
    text_quality_score,
    is_low_quality_video_ocr,
    element_source,
)

from .callbacks import (
    KBIngestCallback,
    KBQueryCallback,
    KBEnqueueIngestCallback,
    KBLoadDocKindsCallback,
)

from .model_fingerprint import (
    FingerprintCollector,
    ModelFingerprint,
    ProbeResult,
    get_fingerprint_collector,
)

from .model_audit import (
    AuditReport,
    ComparisonResult,
    ModelIdentity,
    compare_fingerprints,
    generate_audit_report,
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
    "SimpleEmbedder",
    "SemanticEmbedder",
    "InMemoryRetriever",
    "VectorStoreRetriever",
    "KnowledgeRetriever",
    "create_retriever",
    "create_vector_retriever",
    "create_sqlite_retriever",
    "SqliteEmbeddingRetriever",
    "create_default_embedder",
    "extract_keywords",
    "score_text",
    "text_quality_score",
    "is_low_quality_video_ocr",
    "element_source",
    "KBIngestCallback",
    "KBQueryCallback",
    "KBEnqueueIngestCallback",
    "KBLoadDocKindsCallback",
    "FingerprintCollector",
    "ModelFingerprint",
    "ProbeResult",
    "get_fingerprint_collector",
    "AuditReport",
    "ComparisonResult",
    "ModelIdentity",
    "compare_fingerprints",
    "generate_audit_report",
]
