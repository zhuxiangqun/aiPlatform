"""
Retrieval Quality Gate — CRAG (Corrective RAG) quality check with auto-fallback.

Design principle (RAG article §04):
  When retrieved documents are low quality or irrelevant, blindly feeding them
  to the LLM produces hallucinations. CRAG adds a quality gate: score each chunk,
  and if average falls below threshold, switch to external web search as fallback.

Lightweight: uses heuristic scoring (no extra LLM call needed) by default.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


def _score_chunk(query: str, chunk: str) -> float:
    qwords = set(re.findall(r'[\u4e00-\u9fff\uff00-\uffef]+|[a-zA-Z0-9_]+', str(query).lower()))
    cwords = set(re.findall(r'[\u4e00-\u9fff\uff00-\uffef]+|[a-zA-Z0-9_]+', str(chunk).lower()))
    if not qwords:
        return 0.0
    overlap = len(qwords & cwords)
    return overlap / len(qwords)


def check_quality(
    chunks: List[str],
    query: str,
    threshold: float = 0.3,
    min_chunks: int = 3,
) -> Dict[str, Any]:
    if not chunks or len(chunks) < min_chunks:
        return {"pass": False, "action": "switch_to_web_search", "scores": [],
                "avg_score": 0.0, "reason": f"Not enough chunks ({len(chunks)} < {min_chunks}). Using web search fallback."}

    scores = [_score_chunk(query, c) for c in chunks]
    avg = sum(scores) / max(len(scores), 1)

    if avg >= threshold:
        return {"pass": True, "action": "use_retrieved", "scores": scores,
                "avg_score": round(avg, 3),
                "reason": f"Average relevance {round(avg, 3)} >= threshold {threshold}"}
    return {"pass": False, "action": "switch_to_web_search", "scores": scores,
            "avg_score": round(avg, 3),
            "reason": f"Average relevance {round(avg, 3)} < threshold {threshold}. Using web search fallback."}
