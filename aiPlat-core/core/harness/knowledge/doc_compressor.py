"""
Doc Compressor — token-aware truncation of retrieved documents.

Replaces hard-coded char-based truncation with model-aware token budgeting.
Integrates with MemoryManager for 5-level context compression.
"""
import logging
from typing import Optional

_logger = logging.getLogger(__name__)


def compress_retrieved_docs(docs: str, model_name: str = "",
                            budget_fraction: float = 0.6,
                            max_chars: int = 8000) -> str:
    """Token-aware truncation of retrieved documents.
    
    Keeps retrieved docs within budget_fraction of the model's context window.
    Falls back to char-based truncation when model context size is unknown.
    
    Strategy:
      1. Query model context size from infra ModelManager
      2. Reserve budget_fraction of context for documents
      3. Truncate docs to fit within token budget (≈2 chars per token for CJK)
      4. Fall back to max_chars if model info unavailable
    """
    if not docs:
        return ""

    context_size = _get_context_size(model_name)
    if context_size > 0:
        reserv = 500  # for system prompt + question
        token_budget = int(context_size * budget_fraction) - reserv
        if token_budget < 200:
            token_budget = 200
        # Approx: CJK ~1.5 chars/token, English ~4 chars/token, use 2 as avg
        char_limit = token_budget * 2
        if char_limit < len(docs):
            _logger.info(f"Doc compression: {len(docs)}→{char_limit} chars "
                         f"(model={model_name}, context={context_size}, budget={budget_fraction})")
            return _truncate_smart(docs, char_limit)
    return _truncate_smart(docs, max_chars)


def _get_context_size(model_name: str) -> int:
    """Query model context window size from infra ModelManager."""
    if not model_name:
        return 0
    try:
        from infra.management.model.manager import ModelManager
        mgr = ModelManager()
        for m in mgr._models.values():
            if m.name == model_name or model_name in m.name:
                size = getattr(m, 'context_size', 0) or getattr(m, 'max_tokens', 0)
                if size > 0:
                    return int(size)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # Fallback: known model sizes
    _KNOWN = {
        "qwen": 32768, "deepseek": 128000, "gemma": 131072,
        "llama3": 8192, "mistral": 32768, "mixtral": 32768,
        "gpt-4": 128000, "claude": 200000,
    }
    for prefix, size in _KNOWN.items():
        if model_name.lower().startswith(prefix):
            return size
    return 4096  # default conservative


def _truncate_smart(docs: str, max_chars: int) -> str:
    """Smart truncation: keep first doc fully, rest trimmed."""
    if len(docs) <= max_chars:
        return docs

    parts = docs.split("\n\n---\n\n")
    if len(parts) <= 1:
        return docs[:max_chars]

    result = []
    remaining = max_chars
    for i, part in enumerate(parts):
        if i == 0:
            # Keep first (best-scored) doc fully
            take = min(len(part), remaining)
            result.append(part[:take])
            remaining -= take
        else:
            # Trim subsequent docs
            if remaining < 100:
                break
            take = min(len(part), 300)  # max 300 chars per additional doc
            if take > remaining:
                take = remaining
            result.append(part[:take])
            remaining -= take

    return "\n\n---\n\n".join(result)


def get_model_max_completion(model_name: str = "", default: int = 2000) -> int:
    """Get max completion tokens for a model, adapting to context window size."""
    context = _get_context_size(model_name)
    if context >= 100000:
        return 4096
    elif context >= 32000:
        return 2048
    elif context >= 8000:
        return 1024
    return default
