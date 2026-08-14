"""
Compiled graphs built on aiPlat's internal CompiledGraph engine (core.py).

These graphs support:
- callbacks (persisted to ExecutionStore)
- checkpoints (usable for resuming execution)
"""

from .react import create_compiled_react_graph

__all__ = ["create_compiled_react_graph"]

