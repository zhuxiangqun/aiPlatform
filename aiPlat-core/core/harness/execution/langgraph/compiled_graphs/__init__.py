"""
Compiled graphs built on aiPlat's internal CompiledGraph engine (core.py).

这些 graph 支持：
- callbacks（落库到 ExecutionStore）
- checkpoints（可用于恢复执行）
"""

from .react import create_compiled_react_graph

__all__ = ["create_compiled_react_graph"]

