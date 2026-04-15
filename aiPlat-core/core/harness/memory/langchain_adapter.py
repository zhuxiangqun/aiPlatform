"""
LangChain Memory Adapter

Provides LangChain-compatible memory implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MemoryConfig:
    """Memory configuration"""
    memory_type: str = "buffer"
    max_tokens: int = 2000
    return_messages: bool = True
    output_key: Optional[str] = None
    input_key: str = "input"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryMessage:
    """Memory message"""
    content: str
    type: str = "human"
    metadata: Dict[str, Any] = field(default_factory=dict)


class IMemory(ABC):
    """
    Memory interface - Contract for memory implementations
    """

    @abstractmethod
    async def add_message(self, message: MemoryMessage) -> None:
        """Add message to memory"""
        pass

    @abstractmethod
    async def get_messages(self) -> List[MemoryMessage]:
        """Get all messages"""
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear memory"""
        pass

    @abstractmethod
    async def load_variables(self, variables: Dict[str, Any]) -> None:
        """Load variables into memory"""
        pass

    @abstractmethod
    async def get_context(self, prompt: str) -> str:
        """Get context for prompt"""
        pass


class BufferMemory(IMemory):
    """
    Simple buffer memory using LangChain
    """

    def __init__(self, config: MemoryConfig):
        self._config = config
        self._messages: List[MemoryMessage] = []

    async def add_message(self, message: MemoryMessage) -> None:
        self._messages.append(message)

    async def get_messages(self) -> List[MemoryMessage]:
        return self._messages.copy()

    async def clear(self) -> None:
        self._messages.clear()

    async def load_variables(self, variables: Dict[str, Any]) -> None:
        pass

    async def get_context(self, prompt: str) -> str:
        context_parts = []
        for msg in self._messages:
            prefix = "Human: " if msg.type == "human" else "AI: "
            context_parts.append(f"{prefix}{msg.content}")
        
        if context_parts:
            return "\n".join(context_parts) + f"\nHuman: {prompt}"
        return prompt


class ConversationBufferMemory(IMemory):
    """
    LangChain-based conversation buffer memory
    """

    def __init__(self, config: MemoryConfig):
        self._config = config
        try:
            from langchain.memory import ConversationBufferMemory
            from langchain.schema import BaseMessage
            
            self._lc_memory = ConversationBufferMemory(
                max_token_limit=config.max_tokens,
                return_messages=config.return_messages,
                output_key=config.output_key,
                input_key=config.input_key,
            )
        except ImportError:
            self._lc_memory = None
            self._fallback = BufferMemory(config)

    async def add_message(self, message: MemoryMessage) -> None:
        if self._lc_memory:
            from langchain.schema import HumanMessage, AIMessage
            if message.type == "human":
                msg = HumanMessage(content=message.content)
            else:
                msg = AIMessage(content=message.content)
            await self._lc_memory.aadd_message(msg)
        else:
            await self._fallback.add_message(message)

    async def get_messages(self) -> List[MemoryMessage]:
        if self._lc_memory:
            messages = await self._lc_memory.aget_messages()
            result = []
            for msg in messages:
                msg_type = "ai" if msg.type == "ai" else "human"
                result.append(MemoryMessage(content=msg.content, type=msg_type))
            return result
        return await self._fallback.get_messages()

    async def clear(self) -> None:
        if self._lc_memory:
            await self._lc_memory.aclear()
        else:
            await self._fallback.clear()

    async def load_variables(self, variables: Dict[str, Any]) -> None:
        if self._lc_memory:
            await self._lc_memory.aload_variables(variables)

    async def get_context(self, prompt: str) -> str:
        if self._lc_memory:
            return await self._lc_memory.prompt.get_prompt(
                input_variables=self._lc_memory.input_variables,
                prompt_kwargs={self._lc_memory.input_key: prompt}
            )
        return await self._fallback.get_context(prompt)


def create_memory(config: MemoryConfig) -> IMemory:
    """
    Factory function to create memory instance
    
    Args:
        config: Memory configuration
        
    Returns:
        IMemory: Memory instance
    """
    if config.memory_type == "buffer":
        return BufferMemory(config)
    elif config.memory_type == "buffer_summary":
        return ConversationBufferMemory(config)
    else:
        return BufferMemory(config)


__all__ = [
    "MemoryConfig",
    "MemoryMessage",
    "IMemory",
    "BufferMemory",
    "ConversationBufferMemory",
    "create_memory",
]