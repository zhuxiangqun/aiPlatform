"""Turn summary — format a (question, answer) pair for conversation persistence.

Extracted from MaterialsChatAgent. Chinese locale by default.
"""


def build_turn_summary(question: str, answer: str) -> str:
    """Format a conversation turn into a compact summary string."""
    q = str(question or "").strip()
    a = str(answer or "").strip()
    if not a:
        return f"用户提问：{q}"
    return f"用户提问：{q}；本轮回答要点：{a[:160]}"
