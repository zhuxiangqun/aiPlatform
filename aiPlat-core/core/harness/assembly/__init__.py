"""
Phase 4: Prompt/Context assembly (Kernel-side).

Goal:
- Centralize how prompts/messages are built and versioned, so engines/agents
  do not each implement their own prompt logic.

Phase 4 (minimal):
- Provide PromptAssembler that computes a stable prompt_version hash for a given
  LLM message list (or string prompt).
- Provide ContextAssembler placeholder for future token-budget compaction.
"""

from .prompt_assembler import PromptAssembler, PromptAssemblyResult
from .context_assembler import ContextAssembler, ContextAssemblyResult

__all__ = [
    "PromptAssembler",
    "PromptAssemblyResult",
    "ContextAssembler",
    "ContextAssemblyResult",
]

