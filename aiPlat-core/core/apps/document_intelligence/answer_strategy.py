from __future__ import annotations

from typing import Any, Dict


def choose_answer_strategy(
    *,
    analysis: Dict[str, Any],
    retrieval_policy: Dict[str, Any],
) -> Dict[str, Any]:
    intent = str(analysis.get("intent") or "fact_lookup")
    if intent == "summary":
        return {
            "style": "grounded_summary",
            "need_direct_answer": True,
            "cite_first": False,
            "allow_conditional_answer": False,
            "reason": "summary question should aggregate then cite",
        }
    if intent == "compare":
        return {
            "style": "comparative_analysis",
            "need_direct_answer": True,
            "cite_first": False,
            "allow_conditional_answer": False,
            "reason": "compare question should summarize similarities and differences",
        }
    if intent == "evidence_trace":
        return {
            "style": "evidence_first",
            "need_direct_answer": True,
            "cite_first": True,
            "allow_conditional_answer": False,
            "reason": "evidence trace should prioritize citation and source location",
        }
    if intent == "applicability_analysis":
        return {
            "style": "conditional_analysis",
            "need_direct_answer": True,
            "cite_first": False,
            "allow_conditional_answer": True,
            "reason": "applicability analysis may need conditional answer",
        }
    return {
        "style": "short_grounded",
        "need_direct_answer": True,
        "cite_first": False,
        "allow_conditional_answer": False,
        "reason": f"default fact-style answer for route={retrieval_policy.get('route')}",
    }
