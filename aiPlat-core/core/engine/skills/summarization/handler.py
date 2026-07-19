u"""
Summarization Handler (v2.8) — deterministic LLM summarization.

Wraps sys_llm_generate with summarization-specific prompt template,
providing consistent output format and traceable audit.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger("summarization_handler")


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    u"""Execute summarization with structured prompt.

    Input: { text, max_length?, format? }
    Output: { summary, token_count, model_used }
    """
    text = params.get("text", params.get("content", ""))
    max_length = params.get("max_length", 500)

    if not text:
        return {"summary": "", "error": "No text provided"}

    try:
        from core.harness.utils.model_injection import best_model_for_purpose
        from core.harness.utils.prompt_loader import _sync_resolve

        prompt = _sync_resolve(
            "react-reasoning",
            task=f"Summarize in {max_length} chars: {text[:3000]}",
            history="",
            reasoning="",
            action="",
            observation="",
        )

        model = best_model_for_purpose("doc_llm")
        response = await model.agenerate(prompt)
        summary = getattr(response, "content", str(response))
        usage = getattr(response, "usage", {})
        tokens = usage.get("total_tokens", 0) if isinstance(usage, dict) else 0

        return {
            "summary": summary[:max_length],
            "token_count": tokens,
            "model_used": getattr(model, "model_name", "auto"),
        }
    except Exception as e:
        # Fallback: truncate text as simple summary
        return {
            "summary": text[:max_length] + "...",
            "token_count": 0,
            "model_used": "fallback_truncate",
            "warning": str(e),
        }
