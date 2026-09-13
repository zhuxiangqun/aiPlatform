"""Dynamic spawn policy — factory contracted pipelines disable free multi-agent spawn.

Phase B (W3): StageRunner / sys_agent_call honor this ContextVar + stage field.
Default remains allow (non-factory paths unchanged).
"""
from __future__ import annotations

import contextvars
from typing import Any, Iterator, Optional
from contextlib import contextmanager

_disable_dynamic_spawn: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "aiplat_disable_dynamic_spawn", default=False
)


def is_dynamic_spawn_disabled() -> bool:
    return bool(_disable_dynamic_spawn.get())


def set_dynamic_spawn_disabled(disabled: bool = True) -> contextvars.Token:
    return _disable_dynamic_spawn.set(bool(disabled))


def reset_dynamic_spawn(token: contextvars.Token) -> None:
    _disable_dynamic_spawn.reset(token)


@contextmanager
def disable_dynamic_spawn(disabled: bool = True) -> Iterator[None]:
    """Context manager: temporarily disable DynamicOrchestrator spawn + sys_agent_call."""
    tok = set_dynamic_spawn_disabled(disabled)
    try:
        yield
    finally:
        reset_dynamic_spawn(tok)


def stage_allows_dynamic_spawn(stage: Any) -> bool:
    """PipelineStageConfig.allow_dynamic_spawn (default True)."""
    if stage is None:
        return True
    if isinstance(stage, dict):
        return bool(stage.get("allow_dynamic_spawn", True))
    return bool(getattr(stage, "allow_dynamic_spawn", True))


def should_skip_dynamic_spawn(stage: Optional[Any] = None, state: Optional[dict] = None) -> bool:
    if is_dynamic_spawn_disabled():
        return True
    if state and state.get("_disable_dynamic_spawn"):
        return True
    if stage is not None and not stage_allows_dynamic_spawn(stage):
        return True
    return False
