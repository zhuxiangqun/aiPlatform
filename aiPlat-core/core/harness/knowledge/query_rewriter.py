"""
Query Rewriter — detect and resolve ambiguous / anaphoric queries.

Design principle (RAG article §03 — Conversational RAG):
  Users naturally ask follow-ups like "它多少钱?" without repeating context.
  Two rewrite strategies (zero-cost regex skip, or always-rewrite with full history)
  turn context-dependent queries into standalone retrieval-ready questions.
"""

from __future__ import annotations

import re
from typing import Any, List

_ANAPHORA = re.compile(
    r'(?:它|他|她|这个|那个|这些|那些|这里|那里|上面|前面|刚才|之前)\b|'
    r'\b(?:it|this|that|these|those|the same|the one|above|earlier)\b',
    re.IGNORECASE,
)


def needs_rewrite(query: str, history: List[dict]) -> bool:
    if not _ANAPHORA.search(query or ""):
        return False
    if len(query or "") > 30:
        return False
    return len(history) >= 2


async def rewrite(query: str, history: List[dict], model) -> str:
    """Rewrite anaphoric follow-up into standalone query (single-shot LLM call)."""
    if not history or not model:
        return query
    hist_lines = _format_history(history, max_msgs=6)
    prompt = (
        "Rewrite the following vague follow-up question as a standalone question. "
        "Use the conversation history to resolve pronouns and implicit references.\n\n"
        f"History:\n{hist_lines}\n\n"
        f"Vague question: {query}\n\n"
        "Standalone question:"
    )
    return await _llm_rewrite(model, prompt, query)


async def rewrite_with_history(query: str, history: List[dict], model) -> str:
    """Full conversational rewrite: use up to 10 rounds of history to produce a self-contained query.
    
    Conversational RAG (§03): when users ask follow-up questions in a multi-turn dialogue,
    each query must be rewritten into a standalone form before retrieval, so that the 
    retriever sees a complete question with full context.
    """
    if not history or not model:
        return query
    if len(history) < 2 and not _ANAPHORA.search(query or ""):
        return query
    hist_lines = _format_history(history, max_msgs=10)
    prompt = (
        "Given the conversation history below, rewrite the user's latest question "
        "into a complete, standalone question suitable for information retrieval. "
        "Resolve all pronouns, implicit references, and carry forward the relevant context.\n\n"
        f"Conversation:\n{hist_lines}\n\n"
        f"Latest question: {query}\n\n"
        "Standalone question:"
    )
    return await _llm_rewrite(model, prompt, query)


def _format_history(history: List[dict], max_msgs: int = 6) -> str:
    lines = []
    for m in history[-max_msgs:]:
        role = m.get("role", "?")
        content = str(m.get("content", ""))[:300]
        lines.append(f"[{role}]: {content}")
    return "\n".join(lines)


async def _llm_rewrite(model, prompt: str, fallback: str) -> str:
    try:
        from core.harness.syscalls.llm import sys_llm_generate
        response = await sys_llm_generate(model, prompt, max_tokens=200, trace_context={"source": "query_rewriter"})
        rewritten = getattr(response, "content", str(response)).strip()
        return rewritten if rewritten and len(rewritten) > 5 else fallback
    except Exception:
        return fallback
