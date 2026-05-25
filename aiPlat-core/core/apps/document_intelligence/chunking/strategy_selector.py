"""
Strategy selector — detects document features and chooses the best chunking strategy.

No hardcoded application knowledge. Decisions are driven by structural metrics
extracted from parsed elements.
"""
from __future__ import annotations

from typing import Any, Dict, List


def _count_tokens(text: str) -> int:
    return len(str(text or ""))


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


def detect_features(elements: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not elements:
        return {
            "structure_density": 0.0,
            "paragraph_variance": 0.0,
            "total_tokens": 0,
            "heading_count": 0,
            "element_count": 0,
        }

    n = len(elements)
    headings = 0
    lengths: List[int] = []
    total_tokens = 0

    for el in elements:
        text = str(el.get("text") or "")
        tlen = _count_tokens(text)
        lengths.append(tlen)
        total_tokens += tlen
        if _heading_level(el) > 0:
            headings += 1

    structure_density = headings / n if n > 0 else 0.0

    mean_len = sum(lengths) / n if n > 0 else 0
    variance = sum((l - mean_len) ** 2 for l in lengths) / n if n > 0 else 0.0

    return {
        "structure_density": round(structure_density, 4),
        "paragraph_variance": round(variance, 1),
        "total_tokens": total_tokens,
        "heading_count": headings,
        "element_count": n,
    }


def select_strategy(
    elements: List[Dict[str, Any]],
    kind: str = "pdf",
) -> str:
    """
    Returns one of: structured, recursive, semantic, fixed_size, late.

    Decision tree:
    1. structured: has >= 1 heading AND structure_density > 0.02
    2. semantic: large variance in paragraph lengths (mixed content)
    3. recursive: default for most document types
    4. fixed_size: fallback for very simple text
    """
    feats = detect_features(elements)
    n = feats["element_count"]
    total = feats["total_tokens"]
    headings = feats["heading_count"]
    variance = feats["paragraph_variance"]
    density = feats["structure_density"]

    # Late chunking for very long documents (>20K tokens) without headings
    if total > 20000 and density == 0.0:
        return "late"

    if headings >= 1 and density >= 0.02:
        return "structured"

    if variance > 20000 and n > 5:
        return "semantic"

    if n > 1:
        return "recursive"

    return "fixed_size"
