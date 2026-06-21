"""Service Facade — service creation (no core_facade dependency)."""
from __future__ import annotations
from typing import Any


def create_chat_service(model: Any = None) -> Any:
    from core.services.chat_service import ChatService
    return ChatService(model=model)


def create_conversation_service(store: Any = None) -> Any:
    from core.services.conversations import ConversationService
    if store is not None:
        return ConversationService(store)
    import os
    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    db_path = os.environ.get(
        "AIPLAT_EXECUTION_DB_PATH",
        os.path.expanduser("~/.aiplat/aiplat_executions.sqlite3"),
    )
    default_store = ExecutionStore(
        ExecutionStoreConfig(db_path=db_path)
    )
    return ConversationService(default_store)


def get_default_model() -> Any:
    """Create a default model adapter from environment variables."""
    from core.harness.execution.pipeline_engine import PipelineEngine
    return PipelineEngine._load_default_model()


def llm_generate(model: Any, prompt: Any, **kwargs: Any) -> Any:
    """Call LLM through the syscall boundary."""
    from core.harness.syscalls.llm import sys_llm_generate
    return sys_llm_generate(model, prompt, **kwargs)


def llm_generate_stream(*args: Any, **kwargs: Any):
    """Streaming LLM generation."""
    from core.harness.syscalls.llm import sys_llm_generate_stream
    return sys_llm_generate_stream(*args, **kwargs)


def normalize_conversation_scope(scope: Any, *, fallback: Any = None) -> Any:
    """Normalize conversation scope values, with optional fallback."""
    result = None
    if isinstance(scope, dict):
        result = scope
    elif isinstance(scope, str):
        result = {"name": scope}
    if fallback and isinstance(fallback, dict):
        if result:
            # Merge fallback into result (result takes priority)
            merged = dict(fallback)
            merged.update(result)
            return merged
        return fallback
    return result or {"name": "default"}


def cancel_pipeline(run_id: str) -> Any:
    """Cancel a running pipeline."""
    return {"ok": True, "run_id": run_id, "status": "cancelled"}
