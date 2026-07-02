"""
ReAct Execution Loop — package for SRP-split from monolithic loop.py.

Public API (backward-compatible):
  from core.harness.execution.loop import (
      ReActLoop, BaseLoop, LoopState, LoopConfig, LoopResult
  )

Internal sub-modules:
  - base.py          — BaseLoop infrastructure
  - inference.py     — LLM reasoning engine
  - state_mgr.py     — RunState persistence/restore
  - compressor.py    — Context compaction pipeline
  - graph_injector.py — Knowledge graph injection
  - _facade.py       — ReActLoop facade (coordination only)
"""
from ...interfaces.loop import LoopState, LoopStateEnum, LoopConfig, LoopResult, ILoop
from ._facade import ReActLoop, PlanExecuteLoop, create_loop
from .base import BaseLoop, _infer_task_type, _extract_deny

__all__ = [
    "ReActLoop",
    "PlanExecuteLoop",
    "BaseLoop",
    "create_loop",
    "LoopState",
    "LoopStateEnum",
    "LoopConfig",
    "LoopResult",
    "ILoop",
    "_infer_task_type",
    "_extract_deny",
]
