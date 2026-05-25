"""
Document chunker — splits long text into overlapping or semantic chunks.

Strategies:
  - fixed_size: split by character count with optional overlap
  - semantic: split on paragraph/sentence boundaries under a target size
  - recursive: try semantic first, fallback to fixed_size for very long segments
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def fixed_size_chunks(
    text: str, chunk_size: int = 1000, overlap: int = 200
) -> List[Dict[str, Any]]:
    if not text:
        return []
    chunks: List[Dict[str, Any]] = []
    start = 0
    idx = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append({"text": text[start:end], "chunk_index": idx, "strategy": "fixed_size"})
        idx += 1
        start += chunk_size - overlap
        if start >= len(text):
            break
    return chunks


def semantic_chunks(
    text: str, target_size: int = 1000
) -> List[Dict[str, Any]]:
    if not text:
        return []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[Dict[str, Any]] = []
    current: List[str] = []
    current_len = 0
    idx = 0

    for para in paragraphs:
        p_len = len(para)
        if current_len + p_len > target_size and current:
            chunks.append({"text": "\n\n".join(current), "chunk_index": idx, "strategy": "semantic"})
            idx += 1
            current = []
            current_len = 0
        current.append(para)
        current_len += p_len

    if current:
        chunks.append({"text": "\n\n".join(current), "chunk_index": idx, "strategy": "semantic"})

    return chunks


def recursive_chunks(
    text: str, target_size: int = 1000, overlap: int = 200
) -> List[Dict[str, Any]]:
    if not text:
        return []
    chunks = semantic_chunks(text, target_size)
    result: List[Dict[str, Any]] = []
    idx = 0
    for ch in chunks:
        t = ch["text"]
        if len(t) <= target_size * 1.5:
            result.append({"text": t, "chunk_index": idx, "strategy": "semantic"})
            idx += 1
        else:
            for sub in fixed_size_chunks(t, target_size, overlap):
                result.append({"text": sub["text"], "chunk_index": idx, "strategy": "recursive"})
                idx += 1
    return result


def chunk_document(
    text: str,
    strategy: str = "recursive",
    chunk_size: int = 1000,
    overlap: int = 200,
) -> List[Dict[str, Any]]:
    if strategy == "fixed_size":
        return fixed_size_chunks(text, chunk_size, overlap)
    if strategy == "semantic":
        return semantic_chunks(text, chunk_size)
    return recursive_chunks(text, chunk_size, overlap)


__all__ = ["fixed_size_chunks", "semantic_chunks", "recursive_chunks", "chunk_document"]
