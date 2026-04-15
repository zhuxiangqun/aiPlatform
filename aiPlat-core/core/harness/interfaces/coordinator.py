"""
ICoordinator Interface - Coordinator Contract Definition
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List


@dataclass
class CoordinationResult:
    """Multi-agent coordination result"""
    success: bool
    results: List[Any] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CoordinationConfig:
    """Coordinator configuration"""
    max_agents: int = 5
    timeout: int = 60
    convergence_threshold: float = 0.8
    max_rounds: int = 10
    metadata: Dict[str, Any] = field(default_factory=dict)


class ICoordinator(ABC):
    """
    Coordinator Interface - Core contract for multi-agent coordination
    
    Defines the minimum contract that all coordinator implementations must follow.
    """

    @abstractmethod
    async def coordinate(self, agents: List[Any], task: Any, config: CoordinationConfig) -> CoordinationResult:
        """
        Coordinate multiple agents to complete a task
        
        Args:
            agents: List of agents to coordinate
            task: Task to be completed
            config: Coordination configuration
            
        Returns:
            CoordinationResult: Coordination result
        """
        pass

    @abstractmethod
    async def detect_convergence(self, results: List[Any]) -> bool:
        """
        Detect if multiple agent results have converged
        
        Args:
            results: List of agent results
            
        Returns:
            bool: True if converged, False otherwise
        """
        pass

    @abstractmethod
    async def add_agent(self, agent: Any) -> None:
        """
        Add agent to coordination pool
        
        Args:
            agent: Agent to add
        """
        pass

    @abstractmethod
    async def remove_agent(self, agent_id: str) -> None:
        """
        Remove agent from coordination pool
        
        Args:
            agent_id: ID of agent to remove
        """
        pass

    @abstractmethod
    def get_active_agents(self) -> List[str]:
        """
        Get list of active agent IDs
        
        Returns:
            List[str]: List of agent IDs
        """
        pass