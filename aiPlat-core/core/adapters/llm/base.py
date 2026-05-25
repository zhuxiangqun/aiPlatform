"""
LLM Adapter Base Module

Provides base interface and common functionality for LLM adapters.
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, AsyncIterator
import asyncio


@dataclass
class LLMResponse:
    """LLM response"""
    content: str
    model: str
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AdapterMetadata:
    """Adapter metadata"""
    name: str
    provider: str
    version: str = "1.0.0"
    capabilities: List[str] = field(default_factory=list)
    supports_streaming: bool = False
    supports_functions: bool = False


@dataclass
class LLMConfig:
    """LLM configuration"""
    model: str
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 300
    max_retries: int = 3
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ILLMAdapter(ABC):
    """
    LLM Adapter Interface
    
    Defines the contract for all LLM adapters.
    """

    @property
    @abstractmethod
    def metadata(self) -> AdapterMetadata:
        """Get adapter metadata"""
        pass

    @abstractmethod
    async def generate(
        self,
        messages: List[Dict[str, str]],
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """
        Generate response from messages
        
        Args:
            messages: List of chat messages
            config: Optional configuration override
            
        Returns:
            LLMResponse: Generated response
        """
        pass

    @abstractmethod
    async def stream_generate(
        self,
        messages: List[Dict[str, str]],
        config: Optional[LLMConfig] = None
    ) -> AsyncIterator[str]:
        """
        Stream generate response
        
        Args:
            messages: List of chat messages
            config: Optional configuration override
            
        Yields:
            str: Response chunks
        """
        pass

    @abstractmethod
    async def validate_connection(self) -> bool:
        """Validate API connection"""
        pass


class BaseLLMAdapter(ILLMAdapter):
    """
    Base LLM Adapter Implementation
    
    Provides common functionality for LLM adapters.
    """

    def __init__(
        self,
        metadata: AdapterMetadata,
        config: Optional[LLMConfig] = None
    ):
        self._metadata = metadata
        self._config = config or LLMConfig(model="")

    @property
    def metadata(self) -> AdapterMetadata:
        """Get adapter metadata"""
        return self._metadata

    async def generate(
        self,
        messages: List[Dict[str, str]],
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """Generate response - to be implemented by subclass"""
        raise NotImplementedError("Subclass must implement generate")

    async def stream_generate(
        self,
        messages: List[Dict[str, str]],
        config: Optional[LLMConfig] = None
    ) -> AsyncIterator[str]:
        """Stream generate - to be implemented by subclass"""
        raise NotImplementedError("Subclass must implement stream_generate")

    async def validate_connection(self) -> bool:
        """Validate connection - to be implemented by subclass"""
        raise NotImplementedError("Subclass must implement validate_connection")

    def _merge_config(self, config: Optional[LLMConfig]) -> LLMConfig:
        """Merge provided config with default config"""
        if config is None:
            return self._config
        
        return LLMConfig(
            model=config.model or self._config.model,
            temperature=config.temperature if config.temperature != 0.7 else self._config.temperature,
            max_tokens=config.max_tokens or self._config.max_tokens,
            timeout=config.timeout or self._config.timeout,
            max_retries=config.max_retries or self._config.max_retries,
            api_key=config.api_key or self._config.api_key,
            base_url=config.base_url or self._config.base_url,
        )

    def _build_messages(self, messages: List[Dict[str, str]]) -> List[Any]:
        """Convert messages to provider format - to be overridden"""
        return messages

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse provider response - to be overridden"""
        return LLMResponse(
            content=str(response),
            model=self._config.model,
            usage={}
        )


class RetryableAdapterMixin:
    """Mixin for adding retry logic to adapters"""
    
    async def _generate_with_retry(
        self,
        generate_func: callable,
        *args,
        max_retries: int = 3,
        **kwargs
    ) -> Any:
        """Execute with retry logic"""
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return await generate_func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = 2 ** attempt  # Exponential backoff
                    await asyncio.sleep(delay)
        
        raise last_error


def create_adapter(
    provider: str,
    api_key: Optional[str] = None,
    model: str = "deepseek-chat",
    base_url: Optional[str] = None,
    **kwargs
) -> ILLMAdapter:
    """
    Factory function to create LLM adapter.

    Uses aiPlat-infra LLM client as the primary implementation (via
    InfraLLMAdapter wrapper). Falls back to core's adapters only when:
    - AIPLAT_ENABLE_CORE_ADAPTER_FALLBACK env var is set to "true"
    - Or provider is "mock" / "scripted" (not available in infra)

    Supported infra providers: openai, deepseek, anthropic, local.
    Core-only providers: mock, scripted.
    """
    import importlib
    import os

    # ── Primary path: infra LLM client (wrapped) ──
    if provider not in ("mock", "scripted"):
        try:
            from infra.llm.factory import create_llm_client as _infra_create
            from infra.llm.schemas import LLMConfig
            from core.harness.infrastructure.infra_llm_adapter import InfraLLMAdapter

            infra_config = LLMConfig()
            infra_config.provider = provider
            infra_config.api_key = api_key or ""
            infra_config.model = model
            if base_url:
                infra_config.base_url = base_url
            if kwargs.get("temperature") is not None:
                infra_config.temperature = float(kwargs["temperature"])
            if kwargs.get("max_tokens") is not None:
                infra_config.max_tokens = int(kwargs["max_tokens"])

            client = _infra_create(infra_config)
            adapter: ILLMAdapter = InfraLLMAdapter(client, provider=provider, model=model)
            adapter.model_name = model  # type: ignore[attr-defined]
            return adapter
        except Exception as e:
            # Infra unavailable — provide clear diagnostic
            detail = str(e)[:200]
            raise RuntimeError(
                f"Infra LLM adapter unavailable for provider '{provider}'. "
                f"Core→infra bridge requires aiplat-infra to be installed and the infra service running. "
                f"Error detail: {detail}"
            )

    # ── mock / scripted (test only) ──
    if provider == "mock":
        MockAdapter = importlib.import_module(f"{__package__}.mock_adapter").MockAdapter
        adapter = MockAdapter(model=model, **kwargs)
    elif provider == "scripted":
        ScriptedAdapter = importlib.import_module(f"{__package__}.scripted_adapter").ScriptedAdapter
        adapter = ScriptedAdapter(model=model, **kwargs)
    else:
        raise ValueError(f"Unknown provider: {provider}")

    adapter.model_name = model
    return adapter
