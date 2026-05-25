"""
Knowledge system callback Protocols — Platform → Core reverse-injection contracts.

Core defines the callback signatures it needs. Platform implements them
and registers via kb_provider. This is dependency inversion:
Core depends on the Protocol, not on Platform's concrete types.

Per boundary-standard.md §5.3.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class KBIngestCallback(Protocol):
    """Core → Platform: sync document ingestion callback."""

    def __call__(
        self,
        *,
        tenant_id: str,
        collection_id: str,
        file_path: str,
        kind: str = "pdf",
        ocr_lang: str = "zh",
        ocr_engine: Optional[str] = None,
        dpi: int = 240,
        max_pages: Optional[int] = 60,
        name: str = "",
        progress_cb: Optional[Any] = None,
        last_job_id: Optional[str] = None,
    ) -> Dict[str, Any]: ...


class KBQueryCallback(Protocol):
    """Core → Platform: sync KB query callback (currently budget-focused)."""

    def __call__(
        self,
        *,
        tenant_id: str,
        collection_id: str,
        question: str,
        year: Optional[int] = None,
        limit: int = 50,
    ) -> Dict[str, Any]: ...


class KBEnqueueIngestCallback(Protocol):
    """Core → Platform: async document ingest enqueue callback."""

    def __call__(
        self,
        *,
        tenant_id: str,
        collection_id: str,
        file_path: str,
        kind: str = "pdf",
        ocr_lang: str = "zh",
        ocr_engine: Optional[str] = None,
        dpi: int = 240,
        max_pages: Optional[int] = 60,
        name: str = "",
    ) -> Dict[str, Any]: ...


class KBLoadDocKindsCallback(Protocol):
    """Core → Platform: batch load document kind metadata."""

    def __call__(
        self,
        *,
        tenant_id: str,
        doc_ids: List[str],
    ) -> List[str]: ...


__all__ = [
    "KBIngestCallback",
    "KBQueryCallback",
    "KBEnqueueIngestCallback",
    "KBLoadDocKindsCallback",
]
