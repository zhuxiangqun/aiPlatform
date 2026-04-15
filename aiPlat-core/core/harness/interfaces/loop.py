"""
ILoop Interface - Execution Loop Contract Definition
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List
from enum import Enum


class LoopStateEnum(Enum):
    """Execution loop state enumeration"""
    INIT = "init"
    REASONING = "reasoning"
    ACTING = "acting"
    OBSERVING = "observing"
    FINISHED = "finished"
    ERROR = "error"
    PAUSED = "paused"


@dataclass
class LoopState:
    """Execution loop state"""
    current: LoopStateEnum = LoopStateEnum.INIT
    step_count: int = 0
    used_tokens: int = 0
    max_tokens: int = 8192
    budget_remaining: float = 1.0
    context: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LoopConfig:
    """Loop configuration"""
    max_steps: int = 10
    max_tokens: int = 8192
    budget: float = 1.0
    timeout: int = 60
    stop_on_error: bool = True
    enable_feedback: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LoopResult:
    """Loop execution result"""
    success: bool
    final_state: LoopState = None
    output: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ILoop(ABC):
    """
    Execution Loop Interface - Core contract for loop implementations
    
    Defines the minimum contract that all execution loop implementations must follow.
    """

    @abstractmethod
    async def run(self, state: LoopState, config: LoopConfig) -> LoopResult:
        """
        Run execution loop
        
        Args:
            state: Initial loop state
            config: Loop configuration
            
        Returns:
            LoopResult: Execution result
        """
        pass

    @abstractmethod
    def should_continue(self, state: LoopState) -> bool:
        """
        Determine if loop should continue
        
        Args:
            state: Current loop state
            
        Returns:
            bool: True if should continue, False otherwise
        """
        pass

    @abstractmethod
    async def step(self, state: LoopState) -> LoopState:
        """
        Execute single step
        
        Args:
            state: Current state
            
        Returns:
            LoopState: Updated state
        """
        pass

    @abstractmethod
    def get_current_node(self) -> str:
        """
        Get current execution node name
        
        Returns:
            str: Node name
        """
        pass

    @abstractmethod
    async def reset(self) -> None:
        """
        Reset loop to initial state
        """
        pass