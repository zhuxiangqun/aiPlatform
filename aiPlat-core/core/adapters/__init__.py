"""
Adapters Module

Provides adapters for external services: LLM providers.
"""

from .llm import (
    ILLMAdapter,
    BaseLLMAdapter,
    LLMResponse,
    AdapterMetadata,
    LLMConfig,
    create_adapter,
    OpenAIAdapter,
    AzureOpenAIAdapter,
    AnthropicAdapter,
    ClaudeAdapter,
    LocalAdapter,
    OllamaAdapter,
    VLLMAdapter,
    create_local_adapter,
)

__all__ = [
    "ILLMAdapter",
    "BaseLLMAdapter",
    "LLMResponse",
    "AdapterMetadata",
    "LLMConfig",
    "create_adapter",
    "OpenAIAdapter",
    "AzureOpenAIAdapter",
    "AnthropicAdapter",
    "ClaudeAdapter",
    "LocalAdapter",
    "OllamaAdapter",
    "VLLMAdapter",
    "create_local_adapter",
]