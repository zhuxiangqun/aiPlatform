"""
Hooks System Module
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Callable, Optional
from enum import Enum


class HookPhase(Enum):
    """Hook execution phases"""
    # Execution hooks
    PRE_LOOP = "pre_loop"
    POST_LOOP = "post_loop"
    PRE_REASONING = "pre_reasoning"
    POST_REASONING = "post_reasoning"
    PRE_ACT = "pre_act"
    POST_ACT = "post_act"
    PRE_OBSERVE = "pre_observe"
    POST_OBSERVE = "post_observe"
    
    # Session hooks
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    
    # Tool hooks
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    
    # Skill hooks
    PRE_SKILL_USE = "pre_skill_use"
    POST_SKILL_USE = "post_skill_use"
    
    # Control hooks
    STOP = "stop"
    
    # Contract hooks (Sprint Contract)
    PRE_CONTRACT_CHECK = "pre_contract_check"
    POST_CONTRACT_CHECK = "post_contract_check"
    SCOPE_REVIEW = "scope_review"
    
    # Approval hooks (Human-in-the-Loop)
    PRE_APPROVAL_CHECK = "pre_approval_check"
    POST_APPROVAL_CHECK = "post_approval_check"


@dataclass
class HookContext:
    """Hook execution context"""
    phase: HookPhase
    state: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[Exception] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class Hook(Callable):
    """Hook definition"""
    
    def __init__(
        self,
        name: str,
        callback: Callable,
        phase: HookPhase,
        priority: int = 0
    ):
        self.name = name
        self.callback = callback
        self.phase = phase
        self.priority = priority
    
    async def __call__(self, context: HookContext) -> Any:
        import asyncio
        if asyncio.iscoroutinefunction(self.callback):
            return await self.callback(context)
        return self.callback(context)


class IHookManager(ABC):
    """
    Hook manager interface
    """
    
    @abstractmethod
    def register(self, hook: Hook) -> None:
        """Register a hook"""
        pass
    
    @abstractmethod
    def unregister(self, name: str) -> None:
        """Unregister a hook"""
        pass
    
    @abstractmethod
    async def trigger(self, phase: HookPhase, context: HookContext) -> List[Any]:
        """Trigger hooks for a phase"""
        pass
    
    @abstractmethod
    def get_hooks(self, phase: HookPhase) -> List[Hook]:
        """Get hooks for a phase"""
        pass


class HookManager(IHookManager):
    """
    Default hook manager implementation
    """
    
    def __init__(self):
        self._hooks: Dict[HookPhase, List[Hook]] = {phase: [] for phase in HookPhase}
    
    def register(self, hook: Hook) -> None:
        """Register a hook"""
        self._hooks[hook.phase].append(hook)
        self._hooks[hook.phase].sort(key=lambda h: h.priority, reverse=True)
    
    def unregister(self, name: str) -> None:
        """Unregister a hook by name"""
        for hooks in self._hooks.values():
            for i, hook in enumerate(hooks):
                if hook.name == name:
                    hooks.pop(i)
                    return
    
    async def trigger(self, phase: HookPhase, context: HookContext) -> List[Any]:
        """Trigger hooks for a phase"""
        results = []
        
        for hook in self._hooks[phase]:
            try:
                result = await hook(context)
                results.append(result)
            except Exception as e:
                print(f"Hook {hook.name} failed: {e}")
        
        return results
    
    def get_hooks(self, phase: HookPhase) -> List[Hook]:
        """Get hooks for a phase"""
        return self._hooks[phase].copy()


def create_hook(
    name: str,
    callback: Callable,
    phase: HookPhase,
    priority: int = 0
) -> Hook:
    """Create a hook"""
    return Hook(name=name, callback=callback, phase=phase, priority=priority)


def get_default_hooks() -> Dict[str, Hook]:
    """Get default system hooks"""
    hooks = {}
    
    # Pre-loop hook
    async def pre_loop_hook(context: HookContext):
        context.state = context.state or {}
        context.state["step_count"] = 0
    
    hooks["pre_loop"] = create_hook(
        name="pre_loop",
        callback=pre_loop_hook,
        phase=HookPhase.PRE_LOOP,
        priority=100
    )
    
    # Post-loop hook
    async def post_loop_hook(context: HookContext):
        print(f"Loop completed: {context.state}")
    
    hooks["post_loop"] = create_hook(
        name="post_loop",
        callback=post_loop_hook,
        phase=HookPhase.POST_LOOP,
        priority=100
    )
    
    # Pre-tool-use hook
    async def pre_tool_use_hook(context: HookContext):
        print(f"Tool call: {context.metadata.get('tool_name')}")
    
    hooks["pre_tool_use"] = create_hook(
        name="pre_tool_use",
        callback=pre_tool_use_hook,
        phase=HookPhase.PRE_TOOL_USE,
        priority=50
    )
    
    return hooks