"""
KB application bridge — connects core's generic RAG to platform's concrete KB.

These callbacks are registered by platform at startup (aiPlat-platform/api/rest/routes.py)
and consumed by engine skill handlers and document_intelligence service modules.

Per CLAUDE.md §5.10: Internal Policy modules live in core/apps/.
Per CLAUDE.md §5.29: Core must be application-agnostic — this module is the
adaptation layer between generic core infrastructure and the KB application.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from core.harness.knowledge.callbacks import (
    KBIngestCallback,
    KBQueryCallback,
    KBEnqueueIngestCallback,
    KBLoadDocKindsCallback,
)

_ingest_fn: Optional[KBIngestCallback] = None
_query_fn: Optional[KBQueryCallback] = None
_enqueue_ingest_fn: Optional[KBEnqueueIngestCallback] = None
_load_doc_kinds_fn: Optional[KBLoadDocKindsCallback] = None


def get_tenant_storage(tenant_id: str) -> str:
    """Get tenant-specific storage path under AIPLAT_HOME."""
    base = os.path.expanduser(os.getenv("AIPLAT_HOME", "~/.aiplat"))
    return os.path.join(base, "data", "kb", "tenants", tenant_id)


# ── Ingest ──────────────────────────────────────────────────────────────

def set_knowledge_ingest_fn(fn: KBIngestCallback) -> None:
    global _ingest_fn
    _ingest_fn = fn


def get_ingest_fn() -> KBIngestCallback:
    if _ingest_fn is None:
        raise RuntimeError("KB ingest not initialized. Ensure platform startup calls set_knowledge_ingest_fn()")
    return _ingest_fn


# ── Query ───────────────────────────────────────────────────────────────

def set_kb_query_fn(fn: KBQueryCallback) -> None:
    global _query_fn
    _query_fn = fn


def get_kb_query_fn() -> KBQueryCallback:
    if _query_fn is None:
        raise RuntimeError("KB query not initialized. Ensure platform startup calls set_kb_query_fn()")
    return _query_fn


# ── Enqueue ingest ──────────────────────────────────────────────────────

def set_kb_enqueue_ingest_fn(fn: KBEnqueueIngestCallback) -> None:
    global _enqueue_ingest_fn
    _enqueue_ingest_fn = fn


def get_kb_enqueue_ingest_fn() -> Optional[KBEnqueueIngestCallback]:
    if _enqueue_ingest_fn is None:
        raise RuntimeError("KB enqueue_ingest not initialized.")
    return _enqueue_ingest_fn


# ── Load doc kinds ──────────────────────────────────────────────────────

def set_kb_load_doc_kinds_fn(fn: KBLoadDocKindsCallback) -> None:
    global _load_doc_kinds_fn
    _load_doc_kinds_fn = fn


def get_kb_load_doc_kinds_fn() -> KBLoadDocKindsCallback:
    if _load_doc_kinds_fn is None:
        raise RuntimeError("KB load_doc_kinds not initialized.")
    return _load_doc_kinds_fn


__all__ = [
    "get_tenant_storage",
    "set_knowledge_ingest_fn", "get_ingest_fn",
    "set_kb_query_fn", "get_kb_query_fn",
    "set_kb_enqueue_ingest_fn", "get_kb_enqueue_ingest_fn",
    "set_kb_load_doc_kinds_fn", "get_kb_load_doc_kinds_fn",
]
