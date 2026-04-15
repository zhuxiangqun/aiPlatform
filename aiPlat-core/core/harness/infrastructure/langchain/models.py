"""
LangChain Integration - Models Module
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from enum import Enum


class ModelProvider(Enum):
    """Model provider enumeration"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"
    CUSTOM = "custom"


@dataclass
class ModelConfig:
    """Model configuration"""
    provider: ModelProvider = ModelProvider.OPENAI
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 30
    max_retries: int = 3
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    """Chat message"""
    role: str  # "system", "user", "assistant"
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelResponse:
    """Model response"""
    content: str
    model: str
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    metadata: Dict[str, Any] = field(default_factory=dict)


class IModel(ABC):
    """
    Model interface - Contract for model implementations
    """

    @abstractmethod
    async def generate(
        self,
        messages: List[Message],
        config: Optional[ModelConfig] = None
    ) -> ModelResponse:
        """Generate response from messages"""
        pass

    @abstractmethod
    async def stream_generate(
        self,
        messages: List[Message],
        config: Optional[ModelConfig] = None
    ):
        """Stream generate response"""
        pass

    @abstractmethod
    async def validate_connection(self) -> bool:
        """Validate model connection"""
        pass


class LangChainModelWrapper(IModel):
    """
    LangChain model wrapper
    
    Wraps LangChain chat models to implement IModel interface.
    """

    def __init__(self, chat_model: Any):
        self._chat_model = chat_model

    async def generate(
        self,
        messages: List[Message],
        config: Optional[ModelConfig] = None
    ) -> ModelResponse:
        from langchain.schema import HumanMessage, SystemMessage, AIMessage
        
        lc_messages = []
        for msg in messages:
            if msg.role == "system":
                lc_messages.append(SystemMessage(content=msg.content))
            elif msg.role == "user":
                lc_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                lc_messages.append(AIMessage(content=msg.content))
        
        response = await self._chat_model.agenerate([lc_messages])
        
        return ModelResponse(
            content=response.generations[0][0].text,
            model=getattr(self._chat_model, 'model_name', 'unknown'),
            usage={
                "prompt_tokens": response.llm_output.get("token_usage", {}).get("prompt_tokens", 0),
                "completion_tokens": response.llm_output.get("token_usage", {}).get("completion_tokens", 0),
                "total_tokens": response.llm_output.get("token_usage", {}).get("total_tokens", 0),
            }
        )

    async def stream_generate(
        self,
        messages: List[Message],
        config: Optional[ModelConfig] = None
    ):
        from langchain.schema import HumanMessage, SystemMessage, AIMessage
        
        lc_messages = []
        for msg in messages:
            if msg.role == "system":
                lc_messages.append(SystemMessage(content=msg.content))
            elif msg.role == "user":
                lc_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                lc_messages.append(AIMessage(content=msg.content))
        
        async for chunk in self._chat_model.astream(lc_messages):
            yield chunk.content

    async def validate_connection(self) -> bool:
        try:
            await self._chat_model.agenerate([[HumanMessage(content="test")]])
            return True
        except Exception:
            return False


def create_model(config: ModelConfig) -> IModel:
    """
    Factory function to create model instance
    
    Args:
        config: Model configuration
        
    Returns:
        IModel: Model instance
    """
    if config.provider == ModelProvider.OPENAI:
        from langchain_openai import ChatOpenAI
        chat_model = ChatOpenAI(
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            timeout=config.timeout,
            max_retries=config.max_retries,
            api_key=config.api_key,
            base_url=config.base_url,
        )
        return LangChainModelWrapper(chat_model)
    
    elif config.provider == ModelProvider.ANTHROPIC:
        from langchain_anthropic import ChatAnthropic
        chat_model = ChatAnthropic(
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            timeout=config.timeout,
            anthropic_api_key=config.api_key,
        )
        return LangChainModelWrapper(chat_model)
    
    else:
        raise ValueError(f"Unsupported provider: {config.provider}")