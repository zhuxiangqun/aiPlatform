"""
Infrastructure Module

Provides infrastructure services: LangChain integration, config, lifecycle, hooks, bootstrap, DI, approval.
"""

from .langchain import (
    IModel,
    ModelConfig,
    ModelProvider,
    Message,
    ModelResponse,
    create_model,
    IMemory,
    MemoryConfig,
    create_memory,
    IToolWrapper,
    create_tool_from_function,
    IPromptTemplate,
    create_prompt_template,
)

from .config import (
    Settings,
    IConfigLoader,
    EnvConfigLoader,
    JSONConfigLoader,
    ConfigManager,
    get_config_manager,
)

from .lifecycle import (
    LifecyclePhase,
    LifecycleContext,
    LifecycleHook,
    LifecycleManager,
    ComponentLifecycle,
    create_lifecycle_manager,
)

from .hooks import (
    HookPhase,
    HookContext,
    Hook,
    HookManager,
    create_hook,
    get_default_hooks,
)

from .bootstrap import (
    BootstrapConfig,
    BootstrapResult,
    Bootstrap,
    quick_start,
    quick_shutdown,
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
    # LangChain
    "IModel",
    "ModelConfig",
    "ModelProvider",
    "Message",
    "ModelResponse",
    "create_model",
    "IMemory",
    "MemoryConfig",
    "create_memory",
    "IToolWrapper",
    "create_tool_from_function",
    "IPromptTemplate",
    "create_prompt_template",
    
    # Config
    "Settings",
    "IConfigLoader",
    "EnvConfigLoader",
    "JSONConfigLoader",
    "ConfigManager",
    "get_config_manager",
    
    # Lifecycle
    "LifecyclePhase",
    "LifecycleContext",
    "LifecycleHook",
    "LifecycleManager",
    "ComponentLifecycle",
    "create_lifecycle_manager",
    
    # Hooks
    "HookPhase",
    "HookContext",
    "Hook",
    "HookManager",
    "create_hook",
    "get_default_hooks",
    
    # Bootstrap
    "BootstrapConfig",
    "BootstrapResult",
    "Bootstrap",
    "quick_start",
    "quick_shutdown",
    
    # DI
    "Lifetime",
    "ServiceDescriptor",
    "DIContainer",
    "ContainerBuilder",
    "create_container",
    "create_container_with_defaults",
    
    # Approval (Human-in-the-Loop)
    "RuleType",
    "RequestStatus",
    "ApprovalRule",
    "ApprovalRequest",
    "ApprovalResult",
    "ApprovalContext",
    "ApprovalManager",
    "create_approval_manager",
]