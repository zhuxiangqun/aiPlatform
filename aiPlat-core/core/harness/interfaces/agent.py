"""
IAgent Interface - Agent Contract Definition
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List
from enum import Enum


class AgentStatus(Enum):
    """Agent status enumeration"""
    IDLE = "idle"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class AgentConfig:
    """Agent configuration"""
    name: str
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 30
    max_retries: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentContext:
    """Agent execution context"""
    session_id: str
    user_id: str
    messages: List[Dict[str, str]] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    tools: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    memory: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Agent execution result"""
    success: bool
    output: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    token_usage: Optional[Dict[str, int]] = None


class IAgent(ABC):
    """
    Agent Interface - Core contract for agent implementations
    
    Defines the minimum contract that all agent implementations must follow.
    """

    @abstractmethod
    async def initialize(self, config: AgentConfig) -> None:
        """
        Initialize the agent with configuration
        
        Args:
            config: Agent configuration object
        """
        pass

    @abstractmethod
    async def execute(self, context: AgentContext) -> AgentResult:
        """
        Execute agent with given context
        
        Args:
            context: Agent execution context
            
        Returns:
            AgentResult: Execution result
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """
        Cleanup resources when agent is no longer needed
        """
        pass

    @abstractmethod
    def get_status(self) -> AgentStatus:
        """
        Get current agent status
        
        Returns:
            AgentStatus: Current status
        """
        pass

    @abstractmethod
    async def pause(self) -> None:
        """
        Pause agent execution
        """
        pass

    @abstractmethod
    async def resume(self) -> AgentContext:
        """
        Resume agent execution from paused state
        
        Returns:
            AgentContext: Current context state
        """
        pass