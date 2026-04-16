"""
Kernel syscalls (Phase 2).

Syscalls are the only permitted execution entry points for:
- LLM calls
- Tool calls
- Skill calls

In Phase 2, these are thin wrappers to centralize call semantics and
prepare for gates (policy/trace/context/resilience) to be enforced here.
"""

from .llm import sys_llm_generate
from .tool import sys_tool_call
from .skill import sys_skill_call

__all__ = [
    "sys_llm_generate",
    "sys_tool_call",
    "sys_skill_call",
]

