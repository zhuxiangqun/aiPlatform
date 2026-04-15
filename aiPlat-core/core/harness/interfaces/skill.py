"""
ISkill Interface - Skill Contract Definition
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List


@dataclass
class SkillConfig:
    """Skill configuration"""
    name: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    timeout: int = 60
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillContext:
    """Skill execution context"""
    session_id: str
    user_id: str
    variables: Dict[str, Any] = field(default_factory=dict)
    tools: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillResult:
    """Skill execution result"""
    success: bool
    output: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ISkill(ABC):
    """
    Skill Interface - Core contract for skill implementations
    
    Defines the minimum contract that all skill implementations must follow.
    """

    @abstractmethod
    async def execute(self, context: SkillContext, params: Dict[str, Any]) -> SkillResult:
        """
        Execute skill with given context and parameters
        
        Args:
            context: Skill execution context
            params: Skill parameters
            
        Returns:
            SkillResult: Execution result
        """
        pass

    @abstractmethod
    async def validate(self, params: Dict[str, Any]) -> bool:
        """
        Validate skill parameters
        
        Args:
            params: Parameters to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        pass

    @abstractmethod
    def get_config(self) -> SkillConfig:
        """
        Get skill configuration
        
        Returns:
            SkillConfig: Skill configuration
        """
        pass

    @abstractmethod
    def get_input_schema(self) -> Dict[str, Any]:
        """
        Get skill input schema
        
        Returns:
            Dict: Input schema
        """
        pass

    @abstractmethod
    def get_output_schema(self) -> Dict[str, Any]:
        """
        Get skill output schema
        
        Returns:
            Dict: Output schema
        """
        pass