"""
Infrastructure Module

Provides infrastructure services: config, hooks, DI, approval.
"""

from .config import (
    Settings,
    IConfigLoader,
    EnvConfigLoader,
    JSONConfigLoader,
    ConfigManager,
    get_config_manager,
)

from .hooks import (
    HookPhase,
    HookContext,
    Hook,
    HookManager,
    create_hook,
    get_default_hooks,
)

from .di import (
    Lifetime,
    ServiceDescriptor,
    DIContainer,
    ContainerBuilder,
    create_container,
    create_container_with_defaults,
)

from .approval import (
    RuleType,
    RequestStatus,
    ApprovalRule,
    ApprovalRequest,
    ApprovalResult,
    ApprovalContext,
    ApprovalManager,
    create_approval_manager,
)

__all__ = [
    "Settings",
    "IConfigLoader",
    "EnvConfigLoader",
    "JSONConfigLoader",
    "ConfigManager",
    "get_config_manager",
    "HookPhase",
    "HookContext",
    "Hook",
    "HookManager",
    "create_hook",
    "get_default_hooks",
    "Lifetime",
    "ServiceDescriptor",
    "DIContainer",
    "ContainerBuilder",
    "create_container",
    "create_container_with_defaults",
    "RuleType",
    "RequestStatus",
    "ApprovalRule",
    "ApprovalRequest",
    "ApprovalResult",
    "ApprovalContext",
    "ApprovalManager",
    "create_approval_manager",
]
