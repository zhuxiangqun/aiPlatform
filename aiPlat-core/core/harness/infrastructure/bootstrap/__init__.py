"""
Bootstrap Module - Application Startup and Initialization
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
import asyncio


@dataclass
class BootstrapConfig:
    """Bootstrap configuration"""
    config_path: Optional[str] = None
    enable_auto_register: bool = True
    enable_lifecycle: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BootstrapResult:
    """Bootstrap result"""
    success: bool
    components: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class Bootstrap:
    """
    Default bootstrap implementation
    """
    
    def __init__(self):
        self._steps: List[Callable] = []
        self._components: Dict[str, Any] = {}
        self._lifecycle = None
    
    def add_step(self, step: Callable) -> "Bootstrap":
        """Add a bootstrap step"""
        self._steps.append(step)
        return self
    
    def register_component(self, name: str, component: Any) -> None:
        """Register a component"""
        self._components[name] = component
    
    def get_component(self, name: str) -> Optional[Any]:
        """Get a component"""
        return self._components.get(name)
    
    async def bootstrap(self, config: BootstrapConfig) -> BootstrapResult:
        """Execute bootstrap process"""
        result = BootstrapResult(success=True)
        
        # Step 1: Load configuration
        try:
            from ..config import get_config_manager
            config_manager = get_config_manager()
            settings = config_manager.load()
            self.register_component("settings", settings)
            result.components["settings"] = settings
        except Exception as e:
            result.errors.append(f"Config loading failed: {e}")
        
        # Step 2: Initialize lifecycle
        if config.enable_lifecycle:
            try:
                from ..lifecycle import create_lifecycle_manager
                self._lifecycle = create_lifecycle_manager()
                await self._lifecycle.initialize()
                await self._lifecycle.start()
                self.register_component("lifecycle", self._lifecycle)
                result.components["lifecycle"] = self._lifecycle
            except Exception as e:
                result.errors.append(f"Lifecycle init failed: {e}")
        
        # Step 3: Initialize hooks
        try:
            from ..hooks import HookManager
            hook_manager = HookManager()
            self.register_component("hooks", hook_manager)
            result.components["hooks"] = hook_manager
        except Exception as e:
            result.errors.append(f"Hooks init failed: {e}")
        
        # Step 4: Execute custom steps
        for step in self._steps:
            try:
                if asyncio.iscoroutinefunction(step):
                    await step(self)
                else:
                    step(self)
            except Exception as e:
                result.errors.append(f"Step {step.__name__} failed: {e}")
        
        result.success = len(result.errors) == 0
        return result
    
    async def shutdown(self) -> None:
        """Shutdown application"""
        if self._lifecycle:
            await self._lifecycle.stop()
            await self._lifecycle.destroy()
        
        self._components.clear()


async def quick_start() -> Bootstrap:
    """Quick start bootstrap"""
    bootstrap = Bootstrap()
    config = BootstrapConfig()
    await bootstrap.bootstrap(config)
    return bootstrap


async def quick_shutdown(bootstrap: Bootstrap) -> None:
    """Quick shutdown"""
    await bootstrap.shutdown()


__all__ = [
    "BootstrapConfig",
    "BootstrapResult",
    "Bootstrap",
    "quick_start",
    "quick_shutdown",
]