"""
Adapters Module

All LLM calls route through InfraLLMAdapter (→ infra LLMClient).
Per-provider adapter classes have been retired as of 2026-05.
"""

from .llm import (
    ILLMAdapter,
    BaseLLMAdapter,
    LLMResponse,
    AdapterMetadata,
    LLMConfig,
    create_adapter,
)

__all__ = [
    "ILLMAdapter",
    "BaseLLMAdapter",
    "LLMResponse",
    "AdapterMetadata",
    "LLMConfig",
    "create_adapter",
]
