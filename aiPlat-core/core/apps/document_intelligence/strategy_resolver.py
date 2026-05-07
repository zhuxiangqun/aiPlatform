"""
Strategy resolver — maps route/intent/mode to (effective_strategy, required_skill_ids).

This is an Internal Policy module (per §5.10). It replaces the inline if/elif chain
that was previously hardcoded in MaterialsChatAgent._resolve_strategy().
"""

from __future__ import annotations

from typing import List, Tuple


def resolve_strategy(
    intent: str,
    mode: str,
    route: str,
    default_skill: str,
    doc_count: int = 1,
) -> Tuple[str, List[str]]:
    """Map route + intent to effective strategy and required skill IDs."""
    mode0 = str(mode or "").strip().lower()
    route0 = str(route or "").strip().lower()

    if route0 == "video_fact_lookup":
        return "video_fact_lookup", ["video_fact_lookup"]
    if route0 == "video_window_query":
        if intent == "summary":
            return "video_summary", ["video_window_query"]
        return "video_window_query", ["video_window_query"]
    if route0 == "multi_doc_query":
        if intent == "compare":
            return "multi_doc_compare", ["multi_doc_query"]
        if intent == "summary":
            return "multi_doc_summary", ["multi_doc_query"]
        return "multi_doc_query", ["multi_doc_query"]
    if route0 == "single_doc_query":
        if intent == "summary":
            return "single_doc_summary", [default_skill]
        if intent == "evidence_trace":
            return "single_doc_evidence_trace", [default_skill]
        return "single_doc_query", [default_skill]
    if mode0.startswith("video_window"):
        if intent == "summary":
            return "video_summary", ["video_window_query"]
        return "video_window_query", ["video_window_query"]
    if doc_count > 1:
        if intent == "compare":
            return "multi_doc_compare", ["multi_doc_query"]
        if intent == "summary":
            return "multi_doc_summary", ["multi_doc_query"]
        return "multi_doc_query", ["multi_doc_query"]
    if intent == "summary":
        return "single_doc_summary", [default_skill]
    if intent == "evidence_trace":
        return "single_doc_evidence_trace", [default_skill]
    return "single_doc_query", [default_skill]
