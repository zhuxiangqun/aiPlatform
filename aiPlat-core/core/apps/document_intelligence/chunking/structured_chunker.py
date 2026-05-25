"""
Structured chunker — groups elements by heading structure, then recursively degrades
oversized chunks.

A chunk is a heading + its content elements. If a chunk is too large,
it gets split further using the recursive strategy.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _heading_level(el: Dict[str, Any]) -> int:
    if str(el.get("type") or "").lower() == "heading":
        return int(el.get("meta", {}).get("heading_level") or 1)
    raw = str(el.get("text") or "").strip()
    if raw.startswith("### "):
        return 3
    if raw.startswith("## "):
        return 2
    if raw.startswith("# "):
        return 1
    return 0


def _build_sections(
    elements: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Group elements into sections based on heading hierarchy.

    Each section: {title, level, elements[], texts[]}
    """
    sections: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for el in elements:
        level = _heading_level(el)
        if level > 0:
            title = str(el.get("text") or "").lstrip("#").strip()
            current = {
                "title": title,
                "level": level,
                "elements": [el],
                "texts": [str(el.get("text") or "")],
                "page_idx": int(el.get("page_idx") or 0),
            }
            sections.append(current)
        elif current is not None:
            current["elements"].append(el)
            current["texts"].append(str(el.get("text") or ""))
        else:
            if not sections:
                sections.append({
                    "title": "",
                    "level": 0,
                    "elements": [],
                    "texts": [],
                    "page_idx": int(el.get("page_idx") or 0),
                })
            sections[0]["elements"].append(el)
            sections[0]["texts"].append(str(el.get("text") or ""))

    return [s for s in sections if s["texts"]]


def _count_tokens(text: str) -> int:
    return len(str(text or ""))


def structured_chunk(
    elements: List[Dict[str, Any]],
    target_size: int = 1000,
    overlap: int = 150,
) -> List[Dict[str, Any]]:
    """
    Structured chunking with recursive degradation.

    Returns list of {text, page_idx, meta{...}} chunks.
    """
    if not elements:
        return []

    sections = _build_sections(elements)
    chunks: List[Dict[str, Any]] = []

    from core.harness.document.chunker import recursive_chunks as _recursive

    for idx, sec in enumerate(sections):
        combined = "\n\n".join(sec["texts"])
        total_len = _count_tokens(combined)

        if total_len <= target_size * 1.5:
            chunks.append({
                "text": combined,
                "page_idx": sec["page_idx"],
                "meta": {
                    "chunk_strategy": "structured",
                    "chunk_index": idx,
                    "chunk_total": len(sections),
                    "section_title": sec["title"],
                    "section_level": sec["level"],
                    "element_count": len(sec["elements"]),
                },
            })
        else:
            subs = _recursive(combined, target_size, overlap)
            for si, sub in enumerate(subs):
                chunks.append({
                    "text": sub["text"],
                    "page_idx": sec["page_idx"],
                    "meta": {
                        "chunk_strategy": "structured_recursive",
                        "chunk_index": idx,
                        "sub_index": si,
                        "chunk_total": len(sections),
                        "section_title": sec["title"],
                        "section_level": sec["level"],
                        "element_count": len(sec["elements"]),
                    },
                })

    return chunks
