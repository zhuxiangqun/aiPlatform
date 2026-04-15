from typing import Optional
from .schemas import LLMConfig
from .base import LLMClient


def create(config: Optional[LLMConfig] = None) -> LLMClient:
    """创建 LLM 客户端（便捷函数）"""
    return create_llm_client(config)


def create_llm_client(config: Optional[LLMConfig] = None) -> LLMClient:
    config = config or LLMConfig()

    if config.provider == "openai":
        from .providers import OpenAIClient

        return OpenAIClient(config)
    elif config.provider == "anthropic":
        try:
            from .providers import AnthropicClient

            return AnthropicClient(config)
        except ImportError:
            raise ImportError(
                "anthropic is required for Anthropic support. Install with: pip install anthropic"
            )
    elif config.provider == "deepseek":
        from .providers import DeepSeekClient

        return DeepSeekClient(config)
    elif config.provider == "local":
        from .providers import LocalLLMClient

        return LocalLLMClient(config)
    else:
        raise ValueError(f"Unknown LLM provider: {config.provider}")
