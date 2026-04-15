"""
Context Module

Provides progressive context loading, directory summarization, and trimming.
"""

from .types import (
    LoadStrategy,
    Priority,
    FileContext,
    DirectorySummary,
    LoadedContext,
    TrimmedContext,
    TaskSpec,
)

from .loader import (
    ContextLoader,
    ContextTrimmer,
    create_context_loader,
    create_context_trimmer,
)


__all__ = [
    # Types
    "LoadStrategy",
    "Priority",
    "FileContext",
    "DirectorySummary",
    "LoadedContext",
    "TrimmedContext",
    "TaskSpec",
    # Loader
    "ContextLoader",
    "ContextTrimmer",
    "create_context_loader",
    "create_context_trimmer",
]