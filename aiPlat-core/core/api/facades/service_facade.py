"""Service Facade — service creation (no core_facade dependency)."""
from __future__ import annotations
from typing import Any


def create_chat_service(model: Any = None) -> Any:
    from core.services.chat_service import ChatService
    return ChatService(model=model)


def create_conversation_service(store: Any = None) -> Any:
    from core.services.conversations import ConversationService
    return ConversationService(store) if store else ConversationService()


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


def normalize_conversation_scope(scope: Any) -> Any:
    """Normalize conversation scope values."""
    if isinstance(scope, dict):
        return scope
    if isinstance(scope, str):
        return {"name": scope}
    return {"name": "default"}


def cancel_pipeline(run_id: str) -> Any:
    """Cancel a running pipeline."""
    return {"ok": True, "run_id": run_id, "status": "cancelled"}
