"""
Dependency Injection Module
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type, Callable, get_type_hints
from enum import Enum
import inspect


class Lifetime(Enum):
    """Dependency lifetime"""
    TRANSIENT = "transient"  # New instance each time
    SCOPED = "scoped"        # Same instance per scope
    SINGLETON = "singleton"  # Single instance globally


@dataclass
class ServiceDescriptor:
    """Service descriptor"""
    service_type: Type
    implementation: Any
    lifetime: Lifetime = Lifetime.TRANSIENT


class IDIContainer(ABC):
    """
    DI Container interface
    """
    
    @abstractmethod
    def register(self, service_type: Type, implementation: Any, lifetime: Lifetime = Lifetime.TRANSIENT) -> None:
        """Register a service"""
        pass
    
    @abstractmethod
    def resolve(self, service_type: Type) -> Any:
        """Resolve a service"""
        pass
    
    @abstractmethod
    def create_scope(self) -> "IDIContainer":
        """Create a scoped container"""
        pass


class DIContainer(IDIContainer):
    """
    Default DI container implementation
    """
    
    def __init__(self, parent: Optional["DIContainer"] = None):
        self._services: Dict[Type, ServiceDescriptor] = {}
        self._factories: Dict[Type, Callable] = {}
        self._parent = parent
        self._instances: Dict[Type, Any] = {}
    
    def register(self, service_type: Type, implementation: Any, lifetime: Lifetime = Lifetime.TRANSIENT) -> None:
        """Register a service"""
        if callable(implementation) and not isinstance(implementation, type):
            self._factories[service_type] = implementation
        else:
            self._services[service_type] = ServiceDescriptor(
                service_type=service_type,
                implementation=implementation,
                lifetime=lifetime,
            )
    
    def register_singleton(self, service_type: Type, implementation: Any) -> None:
        """Register a singleton service"""
        self.register(service_type, implementation, Lifetime.SINGLETON)
    
    def register_scoped(self, service_type: Type, implementation: Any) -> None:
        """Register a scoped service"""
        self.register(service_type, implementation, Lifetime.SCOPED)
    
    def resolve(self, service_type: Type) -> Any:
        """Resolve a service"""
        # Check if already instantiated (for singleton/scoped)
        if service_type in self._instances:
            return self._instances[service_type]
        
        # Check parent container
        if self._parent and service_type not in self._services and service_type not in self._factories:
            return self._parent.resolve(service_type)
        
        # Get descriptor
        descriptor = self._services.get(service_type)
        
        if not descriptor and service_type in self._factories:
            factory = self._factories[service_type]
            instance = factory(self)
            if descriptor := self._services.get(service_type):
                if descriptor.lifetime == Lifetime.SINGLETON:
                    self._instances[service_type] = instance
            return instance
        
        if not descriptor:
            # Try to auto-resolve
            return self._auto_resolve(service_type)
        
        # Create instance
        instance = self._create_instance(descriptor)
        
        # Cache if singleton
        if descriptor.lifetime == Lifetime.SINGLETON:
            self._instances[service_type] = instance
        
        return instance
    
    def create_scope(self) -> "DIContainer":
        """Create a scoped container"""
        return DIContainer(parent=self)
    
    def _auto_resolve(self, service_type: Type) -> Any:
        """Auto-resolve a service"""
        init_method = None
        
        # Try to find __init__ method
        if hasattr(service_type, "__init__"):
            init_method = service_type.__init__
        
        if not init_method:
            return service_type()
        
        # Get type hints
        try:
            hints = get_type_hints(init_method)
        except Exception:
            hints = {}
        
        # Resolve dependencies
        kwargs = {}
        for param_name, param_type in hints.items():
            if param_name == "self":
                continue
            try:
                kwargs[param_name] = self.resolve(param_type)
            except Exception:
                pass
        
        return service_type(**kwargs)
    
    def _create_instance(self, descriptor: ServiceDescriptor) -> Any:
        """Create service instance"""
        impl = descriptor.implementation
        
        # If it's a class, instantiate with dependencies
        if isinstance(impl, type):
            return self._auto_resolve(impl)
        
        # If it's a callable, call it with container
        if callable(impl):
            return impl(self)
        
        return impl


class ContainerBuilder:
    """
    DI Container builder for fluent configuration
    """
    
    def __init__(self):
        self._container = DIContainer()
        self._registrations: List[Callable] = []
    
    def register(self, service_type: Type, implementation: Any, lifetime: Lifetime = Lifetime.TRANSIENT) -> "ContainerBuilder":
        """Register a service"""
        self._container.register(service_type, implementation, lifetime)
        return self
    
    def register_singleton(self, service_type: Type, implementation: Any) -> "ContainerBuilder":
        """Register a singleton"""
        return self.register(service_type, implementation, Lifetime.SINGLETON)
    
    def register_scoped(self, service_type: Type, implementation: Any) -> "ContainerBuilder":
        """Register a scoped service"""
        return self.register(service_type, implementation, Lifetime.SCOPED)
    
    def add_registration(self, registration: Callable) -> "ContainerBuilder":
        """Add a registration function"""
        self._registrations.append(registration)
        return self
    
    def build(self) -> DIContainer:
        """Build the container"""
        for registration in self._registrations:
            registration(self._container)
        return self._container


def create_container() -> DIContainer:
    """Create a new DI container"""
    return DIContainer()


def create_container_with_defaults() -> DIContainer:
    """Create container with default registrations"""
    from .config import get_config_manager
    from .lifecycle import create_lifecycle_manager
    from .hooks import HookManager
    
    builder = ContainerBuilder()
    
    builder.register_singleton(
        "config_manager",
        get_config_manager()
    )
    builder.register_singleton(
        "lifecycle",
        create_lifecycle_manager()
    )
    builder.register_singleton(
        "hook_manager",
        HookManager()
    )
    
    return builder.build()