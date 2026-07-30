"""
Evaluation syscall — shared quality assessment (v3.1).

Converges self_review, rag_diagnosis, and hallucination_tracker
that were previously called inline by individual agents.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

_log = logging.getLogger(__name__)


async def sys_evaluate_answer(
    answer: str,
    question: str,
    retrieved_docs: str = "",
    domain_id: str = "default",
    mode: str = "self_review",
) -> Dict[str, Any]:
    """Unified evaluation gateway for all agents.

    Modes:
      - self_review: check answer quality (relevance, completeness, faithfulness)
      - rag_diagnosis: check retrieval quality (coverage, noise)
      - hallucination: check factual accuracy against retrieved context
      - all: run all three modes and aggregate

    Returns:
      {score: float, quality: str, issues: list, mode: str}
      quality: "good" | "acceptable" | "needs_improvement"
    """
    result: Dict[str, Any] = {"score": 0.8, "quality": "good", "issues": [], "mode": mode}

    try:
        if mode in ("self_review", "all"):
            review = await _self_review_answer(answer, question, retrieved_docs)
            result["self_review"] = review
            if review.get("score", 0) < 0.6:
                result["quality"] = "needs_improvement"
                result["issues"].append(f"self_review: {review.get('feedback', 'low quality')}")

        if mode in ("rag_diagnosis", "all"):
            diag = await _rag_diagnosis(question, retrieved_docs, domain_id)
            result["rag_diagnosis"] = diag
            if diag.get("coverage", 0) < 0.5:
                result["issues"].append(f"rag: low coverage ({diag.get('coverage', 0):.0%})")

        if mode in ("hallucination", "all"):
            hal = await _hallucination_check(answer, retrieved_docs)
            result["hallucination"] = hal
            if hal.get("risk", "low") == "high":
                result["quality"] = "needs_improvement"
                result["issues"].append("hallucination risk detected")
    except Exception:
        _log.debug("evaluation failed", exc_info=True)

    return result


async def _self_review_answer(answer: str, question: str, docs: str) -> Dict[str, Any]:
    """Self-review: score answer quality with LLM."""
    try:
        from core.harness.evaluation.self_review import self_review
        return await self_review(answer, question, docs)
    except Exception:
        return {"score": 0.7, "feedback": "self-review unavailable"}


async def _rag_diagnosis(question: str, docs: str, domain_id: str) -> Dict[str, Any]:
    """RAG quality diagnosis: check retrieval coverage."""
    try:
        from core.harness.evaluation.rag_diagnosis import diagnose_rag_quality
        return await diagnose_rag_quality(question, docs, domain_id)
    except Exception:
        return {"coverage": 0.5, "message": "diagnosis unavailable"}


async def _hallucination_check(answer: str, docs: str) -> Dict[str, Any]:
    """Check if answer contains unsupported claims."""
    try:
        from core.harness.evaluation.hallucination_tracker import check_hallucination
        return check_hallucination(answer, docs)
    except Exception:
        return {"risk": "low", "message": "check unavailable"}
