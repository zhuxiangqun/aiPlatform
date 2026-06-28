"""
ISkill Interface - Skill Contract Definition
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List, AsyncGenerator


@dataclass
class SkillConfig:
    """Skill configuration"""
    name: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    timeout: int = 60
    metadata: Dict[str, Any] = field(default_factory=dict)
    effects: List[Dict[str, Any]] = field(default_factory=list)
    idempotent: bool = True
    rollback_available: bool = False

    def __post_init__(self):
        # §5.19: any non-idempotent effect makes the whole skill non-idempotent (unsafe to
        # retry). Derive the top-level flag from per-effect declarations so it always reflects
        # reality — callers building SkillConfig with effects but no explicit idempotent (e.g.
        # the SKILL.md registry path) would otherwise leave it at the default True, silently
        # disabling the §5.19 retry-safety check. Tighten-only: never loosens an explicit value.
        if self.effects and any(
            isinstance(e, dict) and not bool(e.get("idempotent", True)) for e in self.effects
        ):
            self.idempotent = False


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
    priority: str = "medium"


@dataclass
class SkillStreamEvent:
    """A single event yielded during streaming skill execution."""
    event_type: str  # "chunk" | "progress" | "status" | "done"
    data: Any = None
    progress: float = 0.0  # 0.0-1.0
    message: str = ""


class ISkill(ABC):
    """
    Skill Interface - Core contract for skill implementations
    
    Defines the minimum contract that all skill implementations must follow.
    """

    @abstractmethod
    async def execute(self, context: SkillContext, params: Dict[str, Any]) -> SkillResult:
        """
        Execute skill with given context and parameters
        """

    async def execute_stream(
        self, context: SkillContext, params: Dict[str, Any]
    ) -> AsyncGenerator[SkillStreamEvent, None]:
        """
        Execute skill with streaming output. Default falls back to execute().
        Override for skills that can produce incremental output.
        """
        result = await self.execute(context, params)
        yield SkillStreamEvent(event_type="done", data=result, progress=1.0)

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


# ── Skill loader protocol (dependency inversion for harness→apps) ──

from typing import Callable, Optional as OptionalType

SkillLoader = Callable[[str], OptionalType[ISkill]]
"""Protocol: skill loader takes a skill name and returns an ISkill instance.

Allows the harness to use skills without importing from core.apps.skills.
The actual loader is injected at engine construction time.
"""