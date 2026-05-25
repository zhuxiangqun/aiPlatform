"""
Complexity Router — adaptive RAG routing based on query complexity.

Design principle (RAG article §05 — Adaptive RAG):
  Not every query needs the full retrieval pipeline. A simple greeting or fact lookup
  can skip retrieval entirely, saving tokens and latency. Complex analytical queries
  need multi-step retrieval with rerank. This router classifies queries and selects
  the appropriate retrieval strategy without needing an extra model.

Routes:
  "direct"         — no retrieval needed (greetings, known facts)
  "standard_rag"   — standard hybrid retrieval
  "keyword_only"   — exact match lookup (codes, IDs, numbers)
  "multi_step"     — full pipeline with rerank + quality gate (analysis, comparison)
"""

from __future__ import annotations

import re
from typing import Dict, Tuple

_COMPLEX_MARKERS = re.compile(
    r'比较|对比|分析|评估|总结|概括|归纳|review|compare|analyze|evaluate|summarize',
    re.IGNORECASE,
)
_EXACT_MARKERS = re.compile(
    r'[A-Z]{2,}-?\d{2,}|合同编号|订单号|SKU|型号|产品代码|版本号|ISBN|DOI',
)
_QUESTION_MARKERS = re.compile(r'[?？是什么怎么如何多少哪谁什么时候]')
_SHORT_GREETING = re.compile(
    r'^(你好|hi|hello|hey|谢谢|thanks|bye|再见|帮助|help|怎么用|使用说明)\s*$',
    re.IGNORECASE,
)


def classify_complexity(query: str) -> Tuple[str, str]:
    """Classify query and return (route, reason).

    Returns one of: "direct", "standard_rag", "keyword_only", "multi_step"
    """
    if not query or not query.strip():
        return "direct", "empty_query"

    q = query.strip()
    qlen = len(q)

    if _SHORT_GREETING.search(q):
        return "direct", "greeting_or_help"

    if qlen < 5 and not _QUESTION_MARKERS.search(q):
        return "direct", "too_short"

    if _EXACT_MARKERS.search(q):
        return "keyword_only", "exact_match_markers"

    if _COMPLEX_MARKERS.search(q):
        return "multi_step", "complex_markers"

    if qlen > 80:
        return "multi_step", "long_complex_query"

    return "standard_rag", "default"


def route_to_strategy(route: str) -> Dict[str, any]:
    """Map route name to KnowledgeRetriever configuration."""
    defaults = {
        "direct": {
            "skip_retrieval": True,
            "retrieval_strategy": "vector_only",
            "rerank_enabled": False,
            "quality_gate_enabled": False,
        },
        "standard_rag": {
            "skip_retrieval": False,
            "retrieval_strategy": "hybrid",
            "rerank_enabled": False,
            "quality_gate_enabled": False,
        },
        "keyword_only": {
            "skip_retrieval": False,
            "retrieval_strategy": "keyword_only",
            "rerank_enabled": False,
            "quality_gate_enabled": False,
        },
        "multi_step": {
            "skip_retrieval": False,
            "retrieval_strategy": "hybrid",
            "rerank_enabled": True,
            "quality_gate_enabled": True,
        },
    }
    return defaults.get(route, defaults["standard_rag"])
