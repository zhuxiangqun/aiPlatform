"""
Local Model Adapter Module

Provides adapter for local/deployed models (vLLM, Ollama, etc.)
"""

from typing import Any, Dict, List, Optional, AsyncIterator
import os

from .base import (
    BaseLLMAdapter,
    LLMResponse,
    AdapterMetadata,
    LLMConfig,
    RetryableAdapterMixin,
)


class LocalAdapter(BaseLLMAdapter, RetryableAdapterMixin):
    """
    Local Model Adapter
    
    Adapter for locally deployed models (vLLM, Ollama, Text Generation Inference, etc.)
    Supports OpenAI-compatible APIs.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        model: str = "llama-2",
        api_key: Optional[str] = None,
        **kwargs
    ):
        metadata = AdapterMetadata(
            name="local",
            version="1.0.0",
            provider="local",
            capabilities=["text", "chat"],
            supports_streaming=True,
            supports_functions=False,
        )
        
        config = LLMConfig(
            model=model,
            base_url=base_url,
            api_key=api_key or os.getenv("OPENAI_API_KEY"),  # Some local servers need this
            **kwargs
        )
        
        super().__init__(metadata, config)
        self._client = None

    async def generate(
        self,
        messages: List[Dict[str, str]],
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """Generate response using local model API"""
        merged_config = self._merge_config(config)
        
        return await self._generate_with_retry(
            self._generate_impl,
            messages,
            merged_config,
            max_retries=merged_config.max_retries
        )

    async def _generate_impl(
        self,
        messages: List[Dict[str, str]],
        config: LLMConfig
    ) -> LLMResponse:
        """Internal generate implementation"""
        try:
            import openai
            
            client = openai.AsyncOpenAI(
                api_key=config.api_key or "dummy",
                base_url=config.base_url,
            )
            
            response = await client.chat.completions.create(
                model=config.model,
                messages=messages,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            )
            
            return LLMResponse(
                content=response.choices[0].message.content or "",
                model=response.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                },
                finish_reason=response.choices[0].finish_reason or "stop",
            )
            
        except Exception as e:
            return LLMResponse(
                content="",
                model=config.model,
                error=str(e),
            )

    async def stream_generate(
        self,
        messages: List[Dict[str, str]],
        config: Optional[LLMConfig] = None
    ) -> AsyncIterator[str]:
        """Stream generate response"""
        merged_config = self._merge_config(config)
        
        try:
            import openai
            
            client = openai.AsyncOpenAI(
                api_key=merged_config.api_key or "dummy",
                base_url=merged_config.base_url,
            )
            
            response = await client.chat.completions.create(
                model=merged_config.model,
                messages=messages,
                temperature=merged_config.temperature,
                max_tokens=merged_config.max_tokens,
                stream=True,
            )
            
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            yield f"Error: {str(e)}"

    async def validate_connection(self) -> bool:
        """Validate local model connection"""
        try:
            import openai
            
            client = openai.AsyncOpenAI(
                api_key=self._config.api_key or "dummy",
                base_url=self._config.base_url,
            )
            
            # Try to list models
            await client.models.list()
            return True
            
        except Exception:
            return False


class OllamaAdapter(LocalAdapter):
    """
    Ollama-specific adapter
    
    Adapter for Ollama local models.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama2",
        **kwargs
    ):
        # Ollama uses /v1/chat/completions endpoint
        super().__init__(base_url=f"{base_url}/v1", model=model, **kwargs)
        
        self._metadata = AdapterMetadata(
            name="ollama",
            version="1.0.0",
            provider="ollama",
            capabilities=["text", "chat"],
            supports_streaming=True,
            supports_functions=False,
        )

    async def validate_connection(self) -> bool:
        """Validate Ollama connection"""
        try:
            import httpx
            
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self._config.base_url}/models")
                return response.status_code == 200
                
        except Exception:
            return False


class VLLMAdapter(LocalAdapter):
    """
    vLLM-specific adapter
    
    Adapter for vLLM deployed models.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        model: str = "",
        **kwargs
    ):
        super().__init__(base_url=base_url, model=model, **kwargs)
        
        self._metadata = AdapterMetadata(
            name="vllm",
            version="1.0.0",
            provider="vllm",
            capabilities=["text", "chat"],
            supports_streaming=True,
            supports_functions=True,
        )

    async def validate_connection(self) -> bool:
        """Validate vLLM connection"""
        try:
            import httpx
            
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self._config.base_url}/v1/models")
                return response.status_code == 200
                
        except Exception:
            return False


class HuggingFaceTGIAdapter(LocalAdapter):
    """
    Hugging Face Text Generation Inference adapter
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        model: str = "",
        **kwargs
    ):
        super().__init__(base_url=base_url, model=model, **kwargs)
        
        self._metadata = AdapterMetadata(
            name="huggingface-tgi",
            version="1.0.0",
            provider="huggingface",
            capabilities=["text"],
            supports_streaming=True,
            supports_functions=False,
        )

    async def generate(
        self,
        messages: List[Dict[str, str]],
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """Generate using TGI compatible endpoint"""
        merged_config = self._merge_config(config)
        
        try:
            import httpx
            
            # Get last user message as prompt
            prompt = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    prompt = msg.get("content", "")
                    break
            
            async with httpx.AsyncClient(timeout=merged_config.timeout) as client:
                response = await client.post(
                    f"{merged_config.base_url}/generate",
                    json={
                        "inputs": prompt,
                        "parameters": {
                            "temperature": merged_config.temperature,
                            "max_new_tokens": merged_config.max_tokens,
                        }
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return LLMResponse(
                        content=result.get("generated_text", ""),
                        model=merged_config.model,
                    )
                else:
                    return LLMResponse(
                        content="",
                        model=merged_config.model,
                        error=f"HTTP {response.status_code}",
                    )
                    
        except Exception as e:
            return LLMResponse(
                content="",
                model=merged_config.model,
                error=str(e),
            )


def create_local_adapter(
    backend: str = "openai",
    base_url: str = "http://localhost:8000",
    model: str = "",
    **kwargs
) -> LocalAdapter:
    """
    Factory function to create local adapter
    
    Args:
        backend: Backend type ("ollama", "vllm", "tgi", "openai")
        base_url: Base URL
        model: Model name
        
    Returns:
        LocalAdapter: Configured adapter
    """
    if backend == "ollama":
        return OllamaAdapter(base_url=base_url, model=model, **kwargs)
    elif backend == "vllm":
        return VLLMAdapter(base_url=base_url, model=model, **kwargs)
    elif backend == "tgi":
        return HuggingFaceTGIAdapter(base_url=base_url, model=model, **kwargs)
    else:
        return LocalAdapter(base_url=base_url, model=model, **kwargs)