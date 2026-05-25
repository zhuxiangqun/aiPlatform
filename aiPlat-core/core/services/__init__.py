"""
Core Services Module

This module provides common services for aiPlat-core:
- PromptService: Prompt template management and rendering
- ModelService: Unified model access interface
- TraceService: Execution tracing and metrics
- ContextService: Session context and state management
- FileService: File lifecycle management for Agent communication
"""

from .trace_service import TraceService, TraceContext, DecayType
from .context_service import (
    ContextService,
    SessionContext,
    ContextState,
    FileType,
    ContextFile,
)
from .file_service import FileService
from .execution_store import ExecutionStore, ExecutionStoreConfig, get_execution_store

__all__ = [
    "TraceService",
    "TraceContext",
    "DecayType",
    "ContextService",
    "SessionContext",
    "ContextState",
    "FileType",
    "ContextFile",
    "FileService",
    "ExecutionStore",
    "ExecutionStoreConfig",
    "get_execution_store",
]
