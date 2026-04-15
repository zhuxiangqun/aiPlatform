"""
OpenAI Adapter Module

Provides OpenAI API adapter implementation.
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


class OpenAIAdapter(BaseLLMAdapter, RetryableAdapterMixin):
    """
    OpenAI Adapter
    
    Adapter for OpenAI API (GPT-4, GPT-3.5, etc.)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4",
        base_url: Optional[str] = None,
        **kwargs
    ):
        metadata = AdapterMetadata(
            name="openai",
            version="1.0.0",
            provider="openai",
            capabilities=["text", "chat", "functions"],
            supports_streaming=True,
            supports_functions=True,
        )
        
        config = LLMConfig(
            model=model,
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            base_url=base_url,
            **kwargs
        )
        
        super().__init__(metadata, config)
        self._client = None

    async def generate(
        self,
        messages: List[Dict[str, str]],
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """Generate response using OpenAI API"""
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
            from langchain_openai import ChatOpenAI
            
            client = ChatOpenAI(
                model=config.model,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                timeout=config.timeout,
                api_key=config.api_key,
                base_url=config.base_url,
            )
            
            # Convert messages to LangChain format
            lc_messages = self._build_messages(messages)
            
            # Call API
            response = await client.agenerate([lc_messages])
            
            # Parse response
            content = response.generations[0][0].text
            usage = response.llm_output.get("token_usage", {}) if response.llm_output else {}
            
            return LLMResponse(
                content=content,
                model=config.model,
                usage={
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
                finish_reason=response.generations[0][0].generation_info.get("finish_reason", "stop") if response.generations[0][0].generation_info else "stop",
            )
            
        except ImportError:
            # Fallback if langchain not available
            return await self._generate_fallback(messages, config)

    async def _generate_fallback(
        self,
        messages: List[Dict[str, str]],
        config: LLMConfig
    ) -> LLMResponse:
        """Fallback implementation using openai directly"""
        try:
            import openai
            
            client = openai.AsyncOpenAI(
                api_key=config.api_key,
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
                metadata={"error": str(e)},
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
                api_key=merged_config.api_key,
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
        """Validate OpenAI API connection"""
        try:
            import openai
            
            client = openai.AsyncOpenAI(
                api_key=self._config.api_key,
                base_url=self._config.base_url,
            )
            
            await client.models.list()
            return True
            
        except Exception:
            return False

    def _build_messages(self, messages: List[Dict[str, str]]) -> List[Any]:
        """Convert messages to LangChain format"""
        try:
            from langchain.schema import HumanMessage, SystemMessage, AIMessage
            
            lc_messages = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                
                if role == "system":
                    lc_messages.append(SystemMessage(content=content))
                elif role == "user":
                    lc_messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    lc_messages.append(AIMessage(content=content))
                else:
                    lc_messages.append(HumanMessage(content=content))
            
            return lc_messages
            
        except ImportError:
            return messages


class AzureOpenAIAdapter(OpenAIAdapter):
    """
    Azure OpenAI Adapter
    
    Adapter for Azure OpenAI API
    """
    
    def __init__(
        self,
        api_key: str,
        api_version: str = "2024-02-01",
        endpoint: str = "",
        deployment_name: str = "",
        **kwargs
    ):
        super().__init__(api_key=api_key, **kwargs)
        
        self._metadata = AdapterMetadata(
            name="azure-openai",
            version="1.0.0",
            provider="azure-openai",
            capabilities=["text", "chat", "functions"],
            supports_streaming=True,
            supports_functions=True,
        )
        
        self._config.metadata["api_version"] = api_version
        self._config.metadata["endpoint"] = endpoint
        self._config.metadata["deployment_name"] = deployment_name
        self._config.base_url = f"{endpoint}/openai/deployments/{deployment_name}"
    
    async def validate_connection(self) -> bool:
        """Validate Azure OpenAI connection"""
        try:
            import openai
            
            client = openai.AzureOpenAI(
                api_key=self._config.api_key,
                api_version=self._config.metadata.get("api_version", "2024-02-01"),
                azure_endpoint=self._config.metadata.get("endpoint", ""),
            )
            
            await client.models.list()
            return True
            
        except Exception:
            return False