"""
Lifecycle Management Module
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from enum import Enum
import asyncio


class LifecyclePhase(Enum):
    """Lifecycle phases"""
    INIT = "init"
    START = "start"
    RUN = "run"
    STOP = "stop"
    DESTROY = "destroy"


@dataclass
class LifecycleContext:
    """Lifecycle execution context"""
    phase: LifecyclePhase
    metadata: Dict[str, Any] = field(default_factory=dict)


class LifecycleHook(Callable):
    """Lifecycle hook definition"""
    
    def __init__(self, name: str, callback: Callable, phase: LifecyclePhase):
        self.name = name
        self.callback = callback
        self.phase = phase
    
    async def __call__(self, context: LifecycleContext) -> Any:
        if asyncio.iscoroutinefunction(self.callback):
            return await self.callback(context)
        return self.callback(context)


class ILifecycleManager(ABC):
    """
    Lifecycle manager interface
    """
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize lifecycle manager"""
        pass
    
    @abstractmethod
    async def start(self) -> None:
        """Start lifecycle"""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Stop lifecycle"""
        pass
    
    @abstractmethod
    async def destroy(self) -> None:
        """Destroy lifecycle"""
        pass
    
    @abstractmethod
    def register_hook(self, hook: LifecycleHook) -> None:
        """Register lifecycle hook"""
        pass
    
    @abstractmethod
    def get_phase(self) -> LifecyclePhase:
        """Get current phase"""
        pass


class LifecycleManager(ILifecycleManager):
    """
    Default lifecycle manager implementation
    """
    
    def __init__(self):
        self._phase = LifecyclePhase.INIT
        self._hooks: Dict[LifecyclePhase, List[LifecycleHook]] = {
            LifecyclePhase.INIT: [],
            LifecyclePhase.START: [],
            LifecyclePhase.RUN: [],
            LifecyclePhase.STOP: [],
            LifecyclePhase.DESTROY: [],
        }
        self._components: Dict[str, Any] = {}
    
    async def initialize(self) -> None:
        """Initialize lifecycle"""
        await self._execute_hooks(LifecyclePhase.INIT)
        self._phase = LifecyclePhase.INIT
    
    async def start(self) -> None:
        """Start lifecycle"""
        await self._execute_hooks(LifecyclePhase.START)
        self._phase = LifecyclePhase.START
    
    async def stop(self) -> None:
        """Stop lifecycle"""
        await self._execute_hooks(LifecyclePhase.STOP)
        self._phase = LifecyclePhase.STOP
    
    async def destroy(self) -> None:
        """Destroy lifecycle"""
        await self._execute_hooks(LifecyclePhase.DESTROY)
        self._components.clear()
        self._phase = LifecyclePhase.DESTROY
    
    def register_hook(self, hook: LifecycleHook) -> None:
        """Register lifecycle hook"""
        self._hooks[hook.phase].append(hook)
    
    def get_phase(self) -> LifecyclePhase:
        """Get current phase"""
        return self._phase
    
    def register_component(self, name: str, component: Any) -> None:
        """Register a component"""
        self._components[name] = component
    
    def get_component(self, name: str) -> Optional[Any]:
        """Get a component"""
        return self._components.get(name)
    
    async def _execute_hooks(self, phase: LifecyclePhase) -> None:
        """Execute hooks for a phase"""
        context = LifecycleContext(phase=phase)
        
        for hook in self._hooks[phase]:
            try:
                await hook(context)
            except Exception as e:
                print(f"Hook {hook.name} failed: {e}")


class ComponentLifecycle:
    """
    Base class for components with lifecycle support
    """
    
    def __init__(self, name: str):
        self._name = name
        self._lifecycle: Optional[LifecycleManager] = None
    
    async def on_init(self) -> None:
        """Called on initialization"""
        pass
    
    async def on_start(self) -> None:
        """Called on start"""
        pass
    
    async def on_stop(self) -> None:
        """Called on stop"""
        pass
    
    async def on_destroy(self) -> None:
        """Called on destroy"""
        pass
    
    def set_lifecycle(self, lifecycle: LifecycleManager) -> None:
        """Set lifecycle manager"""
        self._lifecycle = lifecycle
    
    @property
    def name(self) -> str:
        """Component name"""
        return self._name


def create_lifecycle_manager() -> LifecycleManager:
    """Create lifecycle manager instance"""
    return LifecycleManager()