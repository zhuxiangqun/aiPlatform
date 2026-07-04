"""Self-RAG lite — post-generation quality check.

Rule-based quality assessment: checks answer length, evidence citations,
and reasoning path depth to assign a quality flag.

Moved from materials_chat.py Phase 1 refactoring.
"""


def self_review(answer: str, citations: list, reasoning_path: list) -> str:
    """Post-generation quality check.

    Returns quality flag: "ok" | "needs_review" | "low_evidence"
    """
    if not answer or len(answer) < 20:
        return "low_evidence"
    has_evidence = bool(citations)
    has_reasoning = len(reasoning_path) >= 2
    if not has_evidence and not has_reasoning:
        return "low_evidence"
    if not has_evidence:
        return "needs_review"
    return "ok"
