"""
Assembly — token budget management and message formatting for LLM context.

TokenBudgetManager (formerly ContextAssembler):
  Token budget allocation, source attribution, message pruning, compression thresholds.

MessageFormatter (formerly PromptAssembler):
  Layer-based context assembly, stable caching, final message structure for LLM consumption.

Call order in loop.py:595-671: TokenBudgetManager → MessageFormatter (pipeline, not parallel).
"""

from .prompt_assembler import MessageFormatter, PromptAssemblyResult
from .context_assembler import (
    BudgetSpec,
    TokenBudgetManager,
    ContextAssemblyResult,
    ContextSource,
    PromptContext,
)

__all__ = [
    "MessageFormatter",
    "PromptAssemblyResult",
    "TokenBudgetManager",
    "ContextAssemblyResult",
    "BudgetSpec",
    "ContextSource",
    "PromptContext",
]

# Backward-compat aliases
ContextAssembler = TokenBudgetManager
PromptAssembler = MessageFormatter
