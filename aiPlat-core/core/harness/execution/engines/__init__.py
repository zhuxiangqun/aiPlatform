"""
Execution engines (Phase 5).

Engines provide a uniform execution surface for different runtime modes:
- loop engine
- langgraph engine
- future agentloop engine

Phase 5.0 minimal:
- Only LoopEngine is used by default (behavior-preserving).
"""

from .base import EngineDecision, IExecutionEngine
from .loop_engine import LoopEngine

__all__ = [
    "EngineDecision",
    "IExecutionEngine",
    "LoopEngine",
]

