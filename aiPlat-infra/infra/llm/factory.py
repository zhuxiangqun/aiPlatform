from typing import Optional, Set
from .schemas import LLMConfig
from .base import LLMClient

# Providers that use the OpenAI-compatible client (same API protocol)
_OPENAI_COMPATIBLE_PROVIDERS: Set[str] = {
    "openai", "deepseek", "qwen", "xai", "lmstudio", "omlx", "vllm",
    "openai_compatible", "ollama", "openrouter",
}


def create(config: Optional[LLMConfig] = None) -> LLMClient:
    """Shortcut for create_llm_client."""
    return create_llm_client(config)


def create_llm_client(config: Optional[LLMConfig] = None) -> LLMClient:
    config = config or LLMConfig()
    provider = (config.provider or "").lower()

    if provider in _OPENAI_COMPATIBLE_PROVIDERS:
        from .providers import OpenAICompatibleClient
        return OpenAICompatibleClient(config)
    elif provider == "anthropic":
        try:
            from .providers import AnthropicClient
            return AnthropicClient(config)
        except ImportError:
            raise ImportError(
                "anthropic package required for Anthropic support. pip install anthropic"
            )
    elif provider == "local":
        from .providers import LocalLLMClient
        return LocalLLMClient(config)
    else:
        raise ValueError(f"Unknown LLM provider: {config.provider}")
