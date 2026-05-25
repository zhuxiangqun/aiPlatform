"""
LLM Adapters Module

All LLM calls route through InfraLLMAdapter (core/harness/infrastructure/infra_llm_adapter.py).
Per-provider adapter classes (OpenAIAdapter, AnthropicAdapter, LocalAdapter) have been retired.
Only mock/scripted adapters remain for testing purposes.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

__all__ = [
    "ILLMAdapter",
    "BaseLLMAdapter",
    "LLMResponse",
    "AdapterMetadata",
    "LLMConfig",
    "create_adapter",
    "MockAdapter",
]

_CANDIDATE_SUBMODULES = (
    "base",
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
    from .mock_adapter import MockAdapter
