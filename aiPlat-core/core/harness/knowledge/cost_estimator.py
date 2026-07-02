"""
Cost Estimator — unified query cost estimation and routing recommendation.

Core capability shared by all Agents. Estimates token cost for RAG vs
full-context routing, with latency prediction and cache-aware savings.

Usage:
    from core.harness.knowledge.cost_estimator import estimate_query_cost

    cost = estimate_query_cost(query="什么是RAG", scope={"doc_ids": ["d1","d2"]})
    # cost.recommendation → "rag_preferred"
    # cost.rag_est_tokens → 8000
    # cost.full_est_tokens → 20000
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CostEstimate:
    """Unified cost estimate for a single query."""

    query_complexity: str = "low"       # "low" | "high"
    doc_count: int = 0
    rag_est_tokens: int = 0             # Estimated RAG token consumption
    full_est_tokens: int = 0            # Estimated full-context token consumption
    cache_saving: int = 0               # Tokens saved if cache hits
    recommendation: str = "direct_llm"  # "rag_required" | "full_context" | "rag_preferred" | "direct_llm"
    latency_est_ms: int = 0             # Estimated latency in ms

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_complexity": self.query_complexity,
            "doc_count": self.doc_count,
            "rag_est_tokens": self.rag_est_tokens,
            "full_est_tokens": self.full_est_tokens,
            "cache_saving": self.cache_saving,
            "recommendation": self.recommendation,
            "latency_est_ms": self.latency_est_ms,
        }


# ── Module-level latency aggregator ──

_latency_buffer: Dict[str, List[float]] = {"rag": [], "full_context": [], "cache": [], "direct_llm": []}
_LATENCY_MAX_SAMPLES = 1000


def record_latency(strategy: str, latency_ms: float) -> None:
    """Record a latency sample for aggregate statistics."""
    if strategy in _latency_buffer:
        buf = _latency_buffer[strategy]
        buf.append(latency_ms)
        if len(buf) > _LATENCY_MAX_SAMPLES:
            buf.pop(0)


def get_latency_stats(strategy: Optional[str] = None) -> Dict[str, Any]:
    """Return P50/P95 latency stats for all or a specific strategy."""
    import statistics

    strategies = [strategy] if strategy else list(_latency_buffer.keys())
    result = {}
    for s in strategies:
        buf = _latency_buffer.get(s, [])
        if not buf:
            result[s] = {"p50_ms": 0, "p95_ms": 0, "samples": 0}
            continue
        buf_sorted = sorted(buf)
        n = len(buf_sorted)
        result[s] = {
            "p50_ms": round(buf_sorted[n // 2]),
            "p95_ms": round(buf_sorted[int(n * 0.95)]),
            "samples": n,
        }
    return result


# ── Cost estimation constants (based on 2026 industry benchmarks) ──

_TOKENS_PER_RAG_CHUNK = 500      # Average tokens per retrieved chunk
_MAX_RAG_CHUNKS = 16             # Cap on RAG chunks
_TOKENS_PER_DOC_CHAR_CN = 2      # ~2 tokens per Chinese character
_AVG_DOC_CHARS = 5000            # Average document size in characters
_RAG_LATENCY_MS = 1500           # Typical RAG latency (1-2s)
_FULL_CTX_LATENCY_MS = 8000      # Typical full-context latency (8-10s)
_DIRECT_LLM_LATENCY_MS = 500     # Typical direct LLM latency
_CACHE_LATENCY_MS = 50           # Typical cache hit latency


def estimate_query_cost(
    query: str,
    scope: Optional[Dict[str, Any]] = None,
    options: Optional[Dict[str, Any]] = None,
) -> CostEstimate:
    """Estimate token cost and recommend routing strategy.

    Args:
        query: User query text
        scope: {"collection_id": str, "doc_ids": [str]}
        options: {"top_k": int, "cache_enabled": bool}

    Returns:
        CostEstimate with recommendation and token breakdown
    """
    scope = scope or {}
    options = options or {}
    top_k = int(options.get("top_k", 8))
    doc_ids = [str(x).strip() for x in (scope.get("doc_ids") or []) if str(x).strip()]
    doc_count = max(len(doc_ids), 1) if doc_ids else 0

    # ── Query complexity ──
    q_len = len(query)
    entity_count = len(re.findall(r"[\u4e00-\u9fff]{2,4}", query))
    is_complex = q_len > 100 or entity_count > 2

    # ── RAG token estimate ──
    if doc_count == 0:
        rag_tokens = 0
    else:
        chunks = min(top_k * doc_count, _MAX_RAG_CHUNKS)
        rag_tokens = chunks * _TOKENS_PER_RAG_CHUNK

    # ── Full-context token estimate ──
    full_tokens = doc_count * _AVG_DOC_CHARS * _TOKENS_PER_DOC_CHAR_CN

    # ── Cache saving ──
    cache_enabled = os.getenv("AIPLAT_SEMANTIC_CACHE_ENABLED", "false").lower() in (
        "true", "1", "yes",
    )
    cache_saving = rag_tokens if cache_enabled else 0

    # ── Routing recommendation ──
    if doc_count == 0:
        rec = "direct_llm"
        latency = _DIRECT_LLM_LATENCY_MS
        rag_tokens = 0
        full_tokens = 0
    elif doc_count <= 2 and not is_complex and full_tokens < 20000:
        rec = "full_context"
        latency = _FULL_CTX_LATENCY_MS
    elif full_tokens > 100000 or doc_count > 10:
        rec = "rag_required"
        latency = _RAG_LATENCY_MS
    elif cache_enabled and rag_tokens > 0:
        rec = "rag_preferred"
        latency = _CACHE_LATENCY_MS
    else:
        rec = "rag_preferred"
        latency = _RAG_LATENCY_MS

    return CostEstimate(
        query_complexity="high" if is_complex else "low",
        doc_count=doc_count,
        rag_est_tokens=rag_tokens,
        full_est_tokens=full_tokens,
        cache_saving=cache_saving,
        recommendation=rec,
        latency_est_ms=latency,
    )


def get_cost_summary(recent: int = 100) -> Dict[str, Any]:
    """Return aggregate cost summary including token savings and strategy distribution."""
    stats = get_latency_stats()
    return {
        "latency_p50_p95": stats,
        "strategy_distribution": {
            s: len(_latency_buffer.get(s, [])) for s in _latency_buffer
        },
        "samples_total": sum(len(v) for v in _latency_buffer.values()),
        "constants": {
            "tokens_per_rag_chunk": _TOKENS_PER_RAG_CHUNK,
            "max_rag_chunks": _MAX_RAG_CHUNKS,
            "avg_doc_chars": _AVG_DOC_CHARS,
        },
    }


__all__ = [
    "CostEstimate",
    "estimate_query_cost",
    "record_latency",
    "get_latency_stats",
    "get_cost_summary",
]
