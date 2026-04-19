"""
Hooks Module
"""

from .hook_manager import (
    HookPhase,
    HookContext,
    Hook,
    IHookManager,
    HookManager,
    create_hook,
    get_default_hooks,
)
from .builtin import (
    HookEvent,
    ExitCode,
    AutoAdaptHook,
    ContextTrackerHook,
    SecurityScanHook,
    PreCommitHook,
    FormatCodeHook,
    TokenLimitHook,
    NotificationHook,
    BUILTIN_HOOKS,
)

from .workspace_loader import load_workspace_hooks

__all__ = [
    "HookPhase",
    "HookContext",
    "Hook",
    "IHookManager",
    "HookManager",
    "create_hook",
    "get_default_hooks",
    "HookEvent",
    "ExitCode",
    "AutoAdaptHook",
    "ContextTrackerHook",
    "SecurityScanHook",
    "PreCommitHook",
    "FormatCodeHook",
    "TokenLimitHook",
    "NotificationHook",
    "BUILTIN_HOOKS",
    "load_workspace_hooks",
]
