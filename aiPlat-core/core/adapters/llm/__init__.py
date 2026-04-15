"""
LLM Adapters Module

Provides adapters for different LLM providers: OpenAI, Anthropic, Local models.
"""

from .base import (
    ILLMAdapter,
    BaseLLMAdapter,
    LLMResponse,
    AdapterMetadata,
    LLMConfig,
    create_adapter,
)

from .openai_adapter import (
    OpenAIAdapter,
    AzureOpenAIAdapter,
)

from .anthropic_adapter import (
    AnthropicAdapter,
    ClaudeAdapter,
)

from .local_adapter import (
    LocalAdapter,
    OllamaAdapter,
    VLLMAdapter,
    HuggingFaceTGIAdapter,
    create_local_adapter,
)

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
]