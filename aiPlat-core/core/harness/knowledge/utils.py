"""
Knowledge retrieval utility functions — text processing helpers.

Extracted from platform/kb/intelligence/query.py per boundary-standard.md §5.2.
These are general text utilities, not application-specific logic.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List


def extract_keywords(text: str) -> List[str]:
    """Extract CJK sequences and alphanumeric tokens from text."""
    text = (text or "").strip()
    if not text:
        return []
    toks: List[str] = []
    toks += re.findall(r"[A-Za-z0-9_]{2,}", text)
    toks += re.findall(r"[\u4e00-\u9fff]{2,}", text)
    seen: set = set()
    out: List[str] = []
    for t in toks:
        if t not in seen:
            out.append(t)
            seen.add(t)
    return out[:20]


def score_text(text: str, keywords: List[str]) -> int:
    """Score text by keyword occurrence count × keyword length."""
    if not text or not keywords:
        return 0
    t = text.lower()
    s = 0
    for k in keywords:
        kk = k.lower()
        s += t.count(kk) * max(1, len(kk) // 2)
    return s


def text_quality_score(text: str) -> float:
    """Estimate text quality by useful-character-to-symbol ratio."""
    s = str(text or "").strip()
    if not s:
        return 0.0
    total = len(s)
    useful = len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", s))
    symbol = len(re.findall(r"[^A-Za-z0-9\u4e00-\u9fff\s]", s))
    return (useful / total) - (symbol / total) * 0.7


def is_low_quality_video_ocr(text: str) -> bool:
    """Detect low-quality OCR output from video frames."""
    s = str(text or "").strip()
    if len(s) < 8:
        return True
    if text_quality_score(s) < 0.28:
        return True
    cjk = len(re.findall(r"[\u4e00-\u9fff]", s))
    latin = len(re.findall(r"[A-Za-z]", s))
    digit = len(re.findall(r"[0-9]", s))
    useful = cjk + latin + digit
    return useful < max(6, len(s) // 4)


def element_source(e: Dict[str, Any]) -> str:
    """Extract the source field from element metadata."""
    meta = e.get("meta")
    if isinstance(meta, dict):
        return str(meta.get("source") or "").strip().lower()
    return ""


__all__ = [
    "extract_keywords",
    "score_text",
    "text_quality_score",
    "is_low_quality_video_ocr",
    "element_source",
]
