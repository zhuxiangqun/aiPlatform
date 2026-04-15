"""
Anthropic Adapter Module

Provides Anthropic API adapter implementation.
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


class AnthropicAdapter(BaseLLMAdapter, RetryableAdapterMixin):
    """
    Anthropic Adapter
    
    Adapter for Anthropic API (Claude models)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-3-opus-20240229",
        **kwargs
    ):
        metadata = AdapterMetadata(
            name="anthropic",
            version="1.0.0",
            provider="anthropic",
            capabilities=["text", "chat"],
            supports_streaming=True,
            supports_functions=False,
        )
        
        config = LLMConfig(
            model=model,
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY"),
            **kwargs
        )
        
        super().__init__(metadata, config)
        self._client = None

    async def generate(
        self,
        messages: List[Dict[str, str]],
        config: Optional[LLMConfig] = None
    ) -> LLMResponse:
        """Generate response using Anthropic API"""
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
            # Try using langchain anthropic
            from langchain_anthropic import ChatAnthropic
            
            client = ChatAnthropic(
                model=config.model,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                timeout=config.timeout,
                anthropic_api_key=config.api_key,
            )
            
            # Convert messages
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
                finish_reason="stop",
            )
            
        except ImportError:
            # Fallback
            return await self._generate_fallback(messages, config)

    async def _generate_fallback(
        self,
        messages: List[Dict[str, str]],
        config: LLMConfig
    ) -> LLMResponse:
        """Fallback implementation using anthropic directly"""
        try:
            import anthropic
            
            client = anthropic.AsyncAnthropic(
                api_key=config.api_key,
                timeout=config.timeout,
            )
            
            # Convert messages to Anthropic format
            system_message = ""
            anthropic_messages = []
            
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                
                if role == "system":
                    system_message = content
                elif role == "user":
                    anthropic_messages.append({
                        "role": "user",
                        "content": content
                    })
                elif role == "assistant":
                    anthropic_messages.append({
                        "role": "assistant",
                        "content": content
                    })
            
            response = await client.messages.create(
                model=config.model,
                messages=anthropic_messages,
                system=system_message if system_message else None,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            )
            
            return LLMResponse(
                content=response.content[0].text if response.content else "",
                model=config.model,
                usage={
                    "input_tokens": response.usage.input_tokens if response.usage else 0,
                    "output_tokens": response.usage.output_tokens if response.usage else 0,
                },
                finish_reason="stop",
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
            import anthropic
            
            client = anthropic.AsyncAnthropic(
                api_key=merged_config.api_key,
                timeout=merged_config.timeout,
            )
            
            # Convert messages
            system_message = ""
            anthropic_messages = []
            
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                
                if role == "system":
                    system_message = content
                elif role == "user":
                    anthropic_messages.append({
                        "role": "user",
                        "content": content
                    })
                elif role == "assistant":
                    anthropic_messages.append({
                        "role": "assistant",
                        "content": content
                    })
            
            async with client.messages.stream(
                model=merged_config.model,
                messages=anthropic_messages,
                system=system_message if system_message else None,
                temperature=merged_config.temperature,
                max_tokens=merged_config.max_tokens,
            ) as stream:
                async for chunk in stream.text_stream:
                    if chunk:
                        yield chunk
                        
        except Exception as e:
            yield f"Error: {str(e)}"

    async def validate_connection(self) -> bool:
        """Validate Anthropic API connection"""
        try:
            import anthropic
            
            client = anthropic.Anthropic(
                api_key=self._config.api_key,
            )
            
            # Simple API call to validate
            client.count_tokens("test")
            return True
            
        except Exception:
            return False

    def _build_messages(self, messages: List[Dict[str, str]]) -> List[Any]:
        """Convert messages to LangChain format"""
        try:
            from langchain.schema import HumanMessage, SystemMessage, AIMessage
            
            lc_messages = []
            system_message = ""
            
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                
                if role == "system":
                    system_message = content
                elif role == "user":
                    lc_messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    lc_messages.append(AIMessage(content=content))
            
            # Anthropic doesn't support system messages in the same way
            # Need to prepend to first user message or use system param
            return lc_messages
            
        except ImportError:
            return messages


class ClaudeAdapter(AnthropicAdapter):
    """
    Claude-specific adapter (alias for AnthropicAdapter)
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-3-opus-20240229",
        **kwargs
    ):
        super().__init__(api_key=api_key, model=model, **kwargs)
        
        self._metadata = AdapterMetadata(
            name="claude",
            version="1.0.0",
            provider="anthropic",
            capabilities=["text", "chat"],
            supports_streaming=True,
            supports_functions=False,
        )