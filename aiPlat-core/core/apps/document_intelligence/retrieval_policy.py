from __future__ import annotations

from typing import Any, Dict, List, Optional


def choose_retrieval_policy(
    *,
    analysis: Dict[str, Any],
    scope: Optional[Dict[str, Any]] = None,
    doc_kinds: Optional[List[str]] = None,
) -> Dict[str, Any]:
    doc_ids = [str(x).strip() for x in ((scope or {}).get("doc_ids") or []) if str(x).strip()]
    doc_count = len(doc_ids)
    intent = str(analysis.get("intent") or "fact_lookup")
    granularity = str(analysis.get("evidence_granularity") or "mixed")
    dominant_doc_kind = str(analysis.get("dominant_doc_kind") or "").strip().lower()

    # single-video summary => video windows
    if doc_count == 1 and dominant_doc_kind in ("video", "mixed_video") and intent == "summary":
        return {
            "route": "video_window_query",
            "skill_name": "knowledge_query",
            "top_k": 4,
            "granularity": "coarse",
            "window_ms": 60000,
            "step_ms": 30000,
            "needs_aggregation": True,
            "retrieval_strategy": "vector_only",
            "rerank_enabled": True,
            "reason": "summary question on single video scope",
        }

    # single-video fact lookup => fine-grained lookup (v1 still via doc_query)
    if doc_count == 1 and dominant_doc_kind in ("video", "mixed_video") and intent in ("fact_lookup", "evidence_trace"):
        return {
            "route": "video_fact_lookup",
            "skill_name": "video_fact_lookup",
            "top_k": 8,
            "granularity": "fine",
            "needs_aggregation": False,
            "reason": "fact/evidence question on single video scope",
        }

    # multi-doc compare/summary
    if doc_count > 1:
        if intent == "compare":
            return {
                "route": "multi_doc_query",
                "skill_name": "knowledge_query",
                "top_k": 8,
                "granularity": "mixed",
                "needs_aggregation": True,
                "reason": "compare question on multi-doc scope",
            }
        if intent == "summary":
            return {
                "route": "multi_doc_query",
                "skill_name": "knowledge_query",
                "top_k": 8,
                "granularity": "coarse",
                "needs_aggregation": True,
                "reason": "summary question on multi-doc scope",
            }
        return {
            "route": "multi_doc_query",
            "skill_name": "multi_doc_query",
            "top_k": 8,
            "granularity": granularity,
            "needs_aggregation": granularity != "fine",
            "retrieval_strategy": "hybrid",
            "rerank_enabled": True,
            "rerank_top_k": 5,
            "quality_gate_enabled": True,
            "quality_threshold": 0.3,
            "reason": "default multi-doc policy",
        }

    # single-doc default
    return {
        "route": "single_doc_query",
        "skill_name": "doc_query",
        "top_k": 8,
        "granularity": granularity if granularity in ("fine", "mixed", "coarse") else "fine",
        "needs_aggregation": granularity == "coarse",
        "reason": "default single-doc policy",
    }
