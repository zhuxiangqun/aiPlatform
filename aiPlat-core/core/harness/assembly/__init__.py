"""
Phase 9: Prompt/Context assembly (Kernel-side).

Goal:
- Centralize how prompts/messages are built and versioned, so engines/agents
  do not each implement their own prompt logic.
- ContextAssembler now provides full PromptContext with token budgeting,
  compaction, and source attribution.
"""

from .prompt_assembler import PromptAssembler, PromptAssemblyResult
from .context_assembler import (
    BudgetSpec,
    ContextAssembler,
    ContextAssemblyResult,
    ContextSource,
    PromptContext,
)

__all__ = [
    "PromptAssembler",
    "PromptAssemblyResult",
    "ContextAssembler",
    "ContextAssemblyResult",
    "BudgetSpec",
    "ContextSource",
    "PromptContext",
]

