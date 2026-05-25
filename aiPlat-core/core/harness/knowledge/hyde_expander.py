"""
HyDE Expander — Hypothetical Document Embeddings for abstract queries.

Design principle (RAG article §08):
  For conceptual or vague queries ("加州数字隐私法律"), the query itself may not
  match any document. HyDE generates a hypothetical answer first, then uses that
  answer's embedding to find similar real documents. The hypothetical answer acts
  as a semantic bridge between the abstract query and concrete documents.

Flow:
  query → LLM generates hypothetical answer → embed hypothetical → retrieve real docs
"""

from __future__ import annotations

from typing import Optional

HYDE_PROMPT = (
    "Write a short passage that answers the following question, even if you have "
    "to speculate. This passage will be used to find relevant documents, so be "
    "specific and factual in tone.\n\n"
    "Question: {query}\n\n"
    "Passage:"
)


async def hyde_expand(query: str, model) -> Optional[str]:
    """Generate a hypothetical document passage for the query.

    Returns the hypothetical text, or None if generation fails.
    The caller should use this text for embedding-based retrieval instead of the raw query.
    """
    if not model or not query:
        return None
    try:
        from core.harness.syscalls.llm import sys_llm_generate
        prompt = HYDE_PROMPT.format(query=query)
        response = await sys_llm_generate(model, prompt, max_tokens=300, trace_context={"source": "hyde_expander"})
        hyde_text = getattr(response, "content", str(response)).strip()
        return hyde_text if hyde_text and len(hyde_text) > 20 else None
    except Exception:
        return None
