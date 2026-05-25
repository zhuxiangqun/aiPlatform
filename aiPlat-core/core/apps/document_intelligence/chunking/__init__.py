"""
Document chunking — strategy selection + structured + recursive strategies.

Usage:
    from core.apps.document_intelligence.chunking import chunk_elements

    chunked = chunk_elements(elements, kind="markdown", target_size=1000)
"""
from __future__ import annotations

from typing import Any, Dict, List

from .strategy_selector import select_strategy
from .structured_chunker import structured_chunk


def chunk_elements(
    elements: List[Dict[str, Any]],
    kind: str = "pdf",
    target_size: int = 1000,
    overlap: int = 150,
) -> List[Dict[str, Any]]:
    """
    Auto-select chunking strategy and apply it to parsed elements.

    Returns list of chunk dicts: {text, page_idx, meta{chunk_strategy, ...}}
    """
    if not elements:
        return []

    strategy = select_strategy(elements, kind)

    if strategy == "structured":
        chunks = structured_chunk(elements, target_size, overlap)
        if chunks:
            return chunks
        strategy = "recursive"

    if strategy in ("recursive", "semantic"):
        from core.harness.document.chunker import (
            recursive_chunks,
            semantic_chunks,
            fixed_size_chunks,
        )

        combined = "\n\n".join(
            str(el.get("text") or "") for el in elements
        )
        if strategy == "semantic":
            raw = semantic_chunks(combined, target_size)
        else:
            raw = recursive_chunks(combined, target_size, overlap)

        return [
            {
                "text": ch["text"],
                "page_idx": elements[0].get("page_idx", 0) if elements else 0,
                "meta": {
                    "chunk_strategy": strategy,
                    "chunk_index": idx,
                    "chunk_total": len(raw),
                },
            }
            for idx, ch in enumerate(raw)
        ]

    # fixed_size fallback
    from core.harness.document.chunker import fixed_size_chunks

    combined = "\n\n".join(
        str(el.get("text") or "") for el in elements
    )
    raw = fixed_size_chunks(combined, target_size, overlap)
    return [
        {
            "text": ch["text"],
            "page_idx": elements[0].get("page_idx", 0) if elements else 0,
            "meta": {
                "chunk_strategy": "fixed_size",
                "chunk_index": idx,
                "chunk_total": len(raw),
            },
        }
        for idx, ch in enumerate(raw)
    ]
