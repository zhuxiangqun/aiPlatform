"""
EngineRouter (Phase 5.0 - minimal).

Phase 5.0 constraints:
- Do not change runtime behavior: agent execution remains loop-first.
- Only add routing metadata (engine/explain/fallback_chain) for observability/audit.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Tuple

from .engines.base import EngineDecision
from .engines.loop_engine import LoopEngine


class EngineRouter:
    def __init__(self) -> None:
        self._loop_engine = LoopEngine()

    def route_agent(self, *, agent_id: str, payload: Dict[str, Any]) -> Tuple[Any, EngineDecision]:
        # Phase 5.0: fixed routing (Loop-first).
        now = time.time()
        decision = EngineDecision(
            engine="loop",
            explain="Phase 5.0: EngineRouter 固定选择 LoopEngine（不改变现有执行路径）",
            fallback_chain=["loop"],
            fallback_trace=[
                {
                    "engine": "loop",
                    "status": "selected",
                    "reason": "固定路由（Phase 5.0/5.1）",
                    "ts": now,
                }
            ],
            metadata={"agent_id": agent_id},
        )
        return self._loop_engine, decision
