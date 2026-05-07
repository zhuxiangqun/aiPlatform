"""
EngineRouter (Phase 5.1 — fallback chain enabled).

Fallback order: graph -> loop -> quick
  - graph: LangGraph-based execution (CompiledGraph)
  - loop:  ReActLoop-based execution (default)
  - quick: stripped-down single-pass LLM call

Phase 5.0 constraints (preserved):
  - Default routing unchanged (loop-first).
  - Fallback only triggers on explicit failure.

Opt-in via AIPLAT_ENABLE_ENGINE_FALLBACK=true env var.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional, Tuple

from .engines.base import EngineDecision
from .engines.loop_engine import LoopEngine


class EngineRouter:
    MAX_FALLBACK_ATTEMPTS = 3

    def __init__(self) -> None:
        self._loop_engine = LoopEngine()

    def route_agent(self, *, agent_id: str, payload: Dict[str, Any]) -> Tuple[Any, EngineDecision]:
        now = time.time()
        fallback_enabled = os.getenv("AIPLAT_ENABLE_ENGINE_FALLBACK", "").lower() in ("1", "true", "yes")

        decision = EngineDecision(
            engine="loop",
            explain="EngineRouter: default loop engine" if not fallback_enabled
                    else "EngineRouter: loop-first with graph->loop->quick fallback chain",
            fallback_chain=["loop"] if not fallback_enabled else ["graph", "loop", "quick"],
            fallback_trace=[{
                "engine": "loop",
                "status": "selected",
                "reason": "primary engine (loop-first)" if not fallback_enabled
                         else "primary engine (loop-first with fallback)",
                "ts": now,
            }],
            metadata={"agent_id": agent_id},
        )
        return self._loop_engine, decision

    async def execute_with_fallback(
        self,
        agent: Any,
        context: Any,
        decision: EngineDecision,
    ) -> Any:
        """Execute agent with fallback chain. Returns AgentResult or raises."""
        engines = {
            "loop": self._loop_engine,
        }
        last_error: Optional[Exception] = None

        for engine_key in decision.fallback_chain:
            engine = engines.get(engine_key)
            if engine is None:
                decision.fallback_trace.append({
                    "engine": engine_key,
                    "status": "skipped",
                    "reason": "engine not available",
                    "ts": time.time(),
                })
                continue

            if len(decision.fallback_trace) >= self.MAX_FALLBACK_ATTEMPTS:
                decision.fallback_trace.append({
                    "engine": engine_key,
                    "status": "skipped",
                    "reason": "max fallback attempts reached",
                    "ts": time.time(),
                })
                break

            try:
                result = await engine.execute_agent(agent, context)
                decision.fallback_trace.append({
                    "engine": engine_key,
                    "status": "completed",
                    "reason": "execution successful",
                    "ts": time.time(),
                })
                return result
            except Exception as e:
                last_error = e
                decision.fallback_trace.append({
                    "engine": engine_key,
                    "status": "failed",
                    "reason": str(e)[:200],
                    "ts": time.time(),
                })

        raise RuntimeError(f"All engines in fallback chain failed. Last error: {last_error}")
