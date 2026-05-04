"""
LLM Adapters Module

Provides adapters for different LLM providers: OpenAI, Anthropic, Local models.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

__all__ = [
    # Base
    "ILLMAdapter",
    "BaseLLMAdapter",
    "LLMResponse",
    "AdapterMetadata",
    "LLMConfig",
    "create_adapter",
    
    # OpenAI
    "OpenAIAdapter",
    "AzureOpenAIAdapter",
    
    # Anthropic
    "AnthropicAdapter",
    "ClaudeAdapter",
    
    # Local
    "LocalAdapter",
    "OllamaAdapter",
    "VLLMAdapter",
    "HuggingFaceTGIAdapter",
    "create_local_adapter",
    "MockAdapter",
]


# Avoid eager imports to reduce circular dependencies (adapters <-> agents <-> execution).
_CANDIDATE_SUBMODULES = (
    "base",
    "openai_adapter",
    "anthropic_adapter",
    "local_adapter",
    "mock_adapter",
    "scripted_adapter",
)


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    for mod in _CANDIDATE_SUBMODULES:
        m = importlib.import_module(f"{__name__}.{mod}")
        if hasattr(m, name):
            return getattr(m, name)
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(__all__))


if TYPE_CHECKING:
    from .base import AdapterMetadata, BaseLLMAdapter, ILLMAdapter, LLMConfig, LLMResponse, create_adapter
    from .anthropic_adapter import AnthropicAdapter, ClaudeAdapter
    from .local_adapter import HuggingFaceTGIAdapter, LocalAdapter, OllamaAdapter, VLLMAdapter, create_local_adapter
    from .mock_adapter import MockAdapter
    from .openai_adapter import AzureOpenAIAdapter, OpenAIAdapter
