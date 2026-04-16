"""
Conversational Agent Module

Provides conversational agent implementation.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .base import BaseAgent, AgentMetadata
from ...harness.interfaces import (
    AgentConfig,
    AgentContext,
    AgentResult,
    AgentStatus,
)
from ...adapters.llm import ILLMAdapter
from ...harness.infrastructure.langchain import MemoryConfig, create_memory, IMemory


@dataclass
class ConversationalAgentConfig:
    """Conversational agent configuration"""
    max_history: int = 10
    max_turns: int = 50
    system_prompt: str = "You are a helpful assistant."
    enable_memory: bool = True
    memory_type: str = "buffer"


class ConversationalAgent(BaseAgent):
    """
    Conversational Agent
    
    Specializes in multi-turn conversations with memory management.
    """

    def __init__(
        self,
        config: AgentConfig,
        model: Optional[ILLMAdapter] = None,
        agent_config: Optional[ConversationalAgentConfig] = None,
        memory: Optional[IMemory] = None,
        **kwargs
    ):
        self._conv_config = agent_config or ConversationalAgentConfig()
        self._memory = memory
        self._turn_count = 0
        self._conversation_history: List[Dict[str, str]] = []
        
        super().__init__(
            config=config,
            model=model,
            **kwargs
        )
        
        self._metadata = AgentMetadata(
            name="ConversationalAgent",
            description="Conversational agent with memory",
            version="1.0.0",
            capabilities=["conversation", "memory", "context_understanding"],
            supported_loop_types=[]
        )
        
        # Initialize memory if enabled
        if self._conv_config.enable_memory and not self._memory:
            mem_config = MemoryConfig(
                memory_type=self._conv_config.memory_type,
                max_tokens=self._conv_config.max_history * 200
            )
            self._memory = create_memory(mem_config)

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute conversational agent"""
        self._status = AgentStatus.RUNNING
        
        try:
            # Add to conversation history
            for msg in context.messages:
                self._conversation_history.append(msg)
            
            # Trim history if needed
            if len(self._conversation_history) > self._conv_config.max_history:
                self._conversation_history = self._conversation_history[-self._conv_config.max_history:]
            
            # Build messages for model
            messages = self._build_messages(context)
            
            # Get response from model
            if not self._model:
                return AgentResult(
                    success=False,
                    error="No model configured"
                )
            from ...harness.syscalls.llm import sys_llm_generate

            response = await sys_llm_generate(self._model, messages)
            
            # Add response to history
            self._conversation_history.append({
                "role": "assistant",
                "content": response.content
            })
            
            # Update memory if enabled
            if self._memory:
                from ...harness.infrastructure.langchain import MemoryMessage
                await self._memory.add_message(MemoryMessage(
                    content=response.content,
                    type="ai"
                ))
            
            self._turn_count += 1
            
            return AgentResult(
                success=True,
                output=response.content,
                token_usage=response.usage,
                metadata={
                    "turns": self._turn_count,
                    "history_length": len(self._conversation_history)
                }
            )
            
        except Exception as e:
            self._status = AgentStatus.ERROR
            return AgentResult(
                success=False,
                error=str(e),
                metadata={"exception": type(e).__name__}
            )

    def _build_messages(self, context: AgentContext) -> List[Dict[str, str]]:
        """Build message list including system prompt and history"""
        messages = []
        
        # Add system prompt
        messages.append({
            "role": "system",
            "content": self._conv_config.system_prompt
        })
        
        # Add conversation history
        messages.extend(self._conversation_history)
        
        # Add current context messages
        if context.messages:
            # Skip system prompt if already in history
            current_msgs = context.messages
            if current_msgs and current_msgs[0].get("role") == "system":
                current_msgs = current_msgs[1:]
            messages.extend(current_msgs)
        
        return messages

    async def reset_conversation(self) -> None:
        """Reset conversation history"""
        self._turn_count = 0
        self._conversation_history = []
        
        if self._memory:
            await self._memory.clear()

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Get conversation history"""
        return self._conversation_history.copy()

    def get_turn_count(self) -> int:
        """Get number of turns"""
        return self._turn_count


def create_conversational_agent(
    config: AgentConfig,
    model: Optional[ILLMAdapter] = None,
    system_prompt: str = "You are a helpful assistant.",
    **kwargs
) -> ConversationalAgent:
    """Create conversational agent"""
    agent_config = ConversationalAgentConfig(system_prompt=system_prompt)
    return ConversationalAgent(config=config, model=model, agent_config=agent_config, **kwargs)
