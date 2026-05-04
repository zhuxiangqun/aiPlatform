"""
Kernel syscalls (Phase 2).

Syscalls are the only permitted execution entry points for:
- LLM calls
- Tool calls
- Skill calls

NOTE: Keep imports lazy to reduce circular dependencies with execution/skills/tools.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

__all__ = ["sys_llm_generate", "sys_tool_call", "sys_skill_call"]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    for mod in ("llm", "tool", "skill"):
        m = importlib.import_module(f"{__name__}.{mod}")
        if hasattr(m, name):
            return getattr(m, name)
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(__all__))


if TYPE_CHECKING:
    from .llm import sys_llm_generate
    from .skill import sys_skill_call
    from .tool import sys_tool_call
