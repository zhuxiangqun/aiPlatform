"""
EngineRouter (Phase 9 — plan-aware routing).

Fallback order: graph -> loop -> quick
  - graph: LangGraph-based execution (CompiledGraph)
  - loop:  ReActLoop-based execution (default)
  - quick: stripped-down single-pass LLM call

Phase 9: ExecutionPlan-aware routing. When a plan is available, the router
injects plan metadata into the agent context for step-by-step execution.
"""

from __future__ import annotations
import logging

import os
import time
from typing import Any, Dict, Optional, Tuple

from .engines.base import EngineDecision
from .engines.loop_engine import LoopEngine
from ..kernel.types import ExecutionPlan


class EngineRouter:
    MAX_FALLBACK_ATTEMPTS = 3

    # Config-driven mapping: agent_type → engine (not hardcoded business strings)
    _GRAPH_ENGINE_TYPES = frozenset({"multi_agent", "multi-agent", "reflection"})

    def __init__(self) -> None:
        self._loop_engine = LoopEngine()
        from .engines.plan_engine import PlanEngine
        from .engines.quick_engine import QuickEngine
        self._plan_engine = PlanEngine(fallback=self._loop_engine)
        self._quick_engine = QuickEngine()
        self._graph_engine = None  # lazy: LangGraph may not be installed

    def route_agent(
        self,
        *,
        agent_id: str,
        payload: Dict[str, Any],
        plan: Optional[ExecutionPlan] = None,
    ) -> Tuple[Any, EngineDecision]:
        now = time.time()
        fallback_enabled = os.getenv("AIPLAT_ENABLE_ENGINE_FALLBACK", "").lower() in ("1", "true", "yes")

        if plan and plan.steps:
            engine, engine_key, chain = self._plan_engine, "plan", ["plan", "loop", "quick"]
        else:
            # Agent-type → graph-type routing (P1-5: previously only reachable via fallback)
            agent_type = payload.get("agent_type", "") if isinstance(payload, dict) else ""
            if agent_type in self._GRAPH_ENGINE_TYPES:
                if self._graph_engine is None:
                    try:
                        from .engines.graph_engine import GraphEngine
                        self._graph_engine = GraphEngine()
                    except Exception as e:
                        logging.warning(str(e), exc_info=True)
                if self._graph_engine is not None:
                    engine, engine_key, chain = self._graph_engine, "graph", ["graph", "loop", "quick"]
                else:
                    engine, engine_key, chain = self._loop_engine, "loop", ["loop", "quick"]
            else:
                # Check for force_react flag in payload options
                options = payload.get("options", {}) if isinstance(payload, dict) else {}
                force_react = options.get("force_react") or options.get("loop_engine") == "react"
                if force_react:
                    engine, engine_key, chain = self._loop_engine, "loop", ["loop", "quick"]
                else:
                    msg_list = payload.get("messages", []) if isinstance(payload, dict) else []
                    if len(msg_list) == 1 and len(str(msg_list[0].get("content", "") or "")) < 100:
                        engine, engine_key, chain = self._quick_engine, "quick", ["quick", "loop"]
                    else:
                        engine, engine_key, chain = self._loop_engine, "loop", ["loop", "quick"]

        if not fallback_enabled:
            chain = [engine_key]

        decision = EngineDecision(
            engine=engine_key,
            explain=f"EngineRouter: {engine_key} engine" if not fallback_enabled
                    else f"EngineRouter: {engine_key}-first with {chain} fallback chain",
            fallback_chain=chain,
            fallback_trace=[{
                "engine": engine_key,
                "status": "selected",
                "reason": f"primary engine ({engine_key}-first)" if not fallback_enabled
                         else f"primary engine ({engine_key}-first with fallback)",
                "ts": now,
            }],
            metadata={
                "agent_id": agent_id,
                "plan_available": plan is not None and bool(plan.steps) if plan else False,
                "plan_steps": len(plan.steps) if plan and plan.steps else 0,
            },
        )
        return engine, decision

    async def execute_with_fallback(
        self,
        agent: Any,
        context: Any,
        decision: EngineDecision,
    ) -> Any:
        """Execute agent with fallback chain. Returns AgentResult or raises."""
        engines: Dict[str, Any] = {
            "plan": self._plan_engine,
            "loop": self._loop_engine,
            "quick": self._quick_engine,
        }
        if self._graph_engine is None:
            try:
                from .engines.graph_engine import GraphEngine
                self._graph_engine = GraphEngine()
            except Exception as e:
                logging.warning(str(e), exc_info=True)
        if self._graph_engine is not None:
            engines["graph"] = self._graph_engine
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
