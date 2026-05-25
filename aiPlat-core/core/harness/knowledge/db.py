"""
Knowledge DB provider — generic retrieval infrastructure.

The concrete knowledge DB (KBSqlite) lives in aiPlat-platform/kb/.
Core accesses it through set_knowledge_db()/get_knowledge_db() provider pattern,
breaking the core→platform reverse dependency.

KB-specific bridge callbacks (ingest, query, enqueue) are in
core/apps/document_intelligence/kb_provider.py per CLAUDE.md §5.10
(Internal Policy — adaptation layer between generic RAG and KB application).

Per CLAUDE.md §5.10: knowledge/ is generic RAG infrastructure — types, retrieval,
embedding, provider pattern. Application-specific KB bridges belong in
document_intelligence/.
"""

from __future__ import annotations

from typing import Any

_knowledge_db: Any = None


def set_knowledge_db(db: Any) -> None:
    """Called at platform startup to inject the concrete KBSqlite instance."""
    global _knowledge_db
    _knowledge_db = db


def get_knowledge_db() -> Any:
    """Get the injected KBSqlite. Engine skills call this instead of importing directly."""
    if _knowledge_db is None:
        raise RuntimeError(
            "KnowledgeDB not initialized. "
            "Ensure platform startup calls set_knowledge_db(KBSqlite(...))"
        )
    return _knowledge_db


__all__ = ["set_knowledge_db", "get_knowledge_db"]
