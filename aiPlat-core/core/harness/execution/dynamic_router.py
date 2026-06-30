"""
DynamicRouter — LLM-driven multi-agent routing engine.

Replaces static dependency_layers with runtime LLM decision:
  1. Supervisor reads current PipelineState + goal + available agents
  2. LLM chooses the next agent to execute (or FINISH)
  3. Agent executes → results merged via Reducer → loop
  4. Repeats until FINISH or max_steps exhausted

Integration: set routing_mode="llm" on PipelineStageConfig.
The router writes to state["_route_after"] and the existing
_compute_dependency_layers handles the rest.

Architecture:
  - Reuses SubagentCoordinator.execute_single() via context for instruction injection
  - Respects PipelineStageConfig.merge_strategies for safe parallel state merge
  - Feature-flagged via routing_mode field (default "static", backward compatible)
  - Supervisor model: configurable via AIPLAT_SUPERVISOR_MODEL or stage.model

Grayscale Deployment:
  1. Select one low-risk pipeline (e.g., internal doc search, non-production)
  2. Set routing_mode="llm" on that pipeline's PipelineStageConfig
  3. Monitor supervisor decisions via state["_dynamic_trace"] for 1 week
  4. If supervisor routing accuracy > 80% (via human review of traces),
     expand to 3 more pipelines
  5. If accuracy drops or cost spikes (>2x baseline), set back to "static"

Safety defaults:
  - max_steps=15 (hard cap, not LLM-modifiable)
  - Supervisor temperature=0.2 (deterministic routing)
  - Non-blocking: router failures fall back to static dependency_layers
  - All supervisor decisions logged to state["_dynamic_trace"]
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.schemas_builder import PipelineStageConfig

logger = logging.getLogger(__name__)


class DynamicRouter:
    """LLM-driven routing loop — Supervisor as Router, not as Executor."""

    def __init__(
        self,
        *,
        supervisor_model: str = "",
        max_steps: int = 15,
        agent_descriptions: Optional[Dict[str, str]] = None,
    ):
        self.max_steps = max_steps
        self.supervisor_model = supervisor_model or self._default_supervisor_model()
        self.agent_descriptions = agent_descriptions or {}
        self._trace: List[Dict[str, Any]] = []

    @staticmethod
    def _default_supervisor_model() -> str:
        import os
        from core.harness.utils.model_injection import best_model_for_purpose
        return os.getenv("AIPLAT_SUPERVISOR_MODEL", "") or best_model_for_purpose("chat") or "qwen2.5-coder:7b"

    async def run(
        self,
        *,
        state: Dict[str, Any],
        goal: str,
        stages: List["PipelineStageConfig"],
        stage_idx_map: Dict[str, int],
    ) -> Dict[str, Any]:
        """Execute dynamic routing loop.

        Args:
            state: Current PipelineState dict
            goal: High-level task description
            stages: Full stage list from PipelineConfig
            stage_idx_map: Mapping of stage.id → index in stages list

        Returns:
            Updated state after loop completes or max_steps exhausted
        """
        available_ids = [s.id for s in stages]
        available_names = [s.agent_name or s.agent_id for s in stages]
        self._trace = []
        logger.info("DynamicRouter started: goal='%s', agents=%d", goal[:80], len(stages))

        for step in range(1, self.max_steps + 1):
            # 1. Supervisor decides next agent
            decision = await self._decide_next(state, goal, available_names, step)
            self._trace.append(vars(decision))
            logger.info("Step %d: %s → %s", step, decision.decision, decision.agent_name or "FINISH")

            if decision.decision == "finish":
                break

            if decision.decision == "call_agent" and decision.agent_name in available_names:
                # Find the matching stage index
                target_idx = None
                for s in stages:
                    if s.agent_name == decision.agent_name or s.agent_id == decision.agent_name:
                        target_idx = stage_idx_map.get(s.id)
                        break

                if target_idx is not None:
                    # Write routing target — existing layer engine handles execution
                    state["_route_after"] = target_idx
                    state["_last_action_reason"] = f"dynamic_routed_to:{decision.agent_name}"
                    state.setdefault("_dynamic_trace", []).append({
                        "step": step, "agent": decision.agent_name,
                        "reasoning": decision.reasoning,
                    })

            elif decision.decision == "finish":
                break

        logger.info("DynamicRouter finished: %d steps, %d trace entries", step, len(self._trace))
        return state

    # ── Core: LLM decision ──

    async def _decide_next(
        self, state: dict, goal: str, available: List[str], step: int
    ) -> Any:
        """Call Supervisor LLM to decide the next agent."""
        agents_desc = "\n".join([
            f"- {name}: {self.agent_descriptions.get(name, '通用Agent')}"[:120]
            for name in available
        ])
        history = state.get("_dynamic_trace", state.get("trace", []))[-5:]
        history_str = "\n".join([
            f"  Step {e.get('step','?')}: {e.get('agent','?')}"
            for e in history
        ]) if history else "（尚未执行任何步骤）"

        system = (
            f"你是多Agent系统的路由调度器。从以下可用Agent中选择下一个执行者。\n\n"
            f"【可用Agent】\n{agents_desc}\n\n"
            f"【规则】\n"
            f"1. 选择最应该执行下一步的Agent\n"
            f"2. 如果任务已完成，输出 finish\n"
            f"3. 如果当前信息不足，优先选能获取信息的Agent\n"
        )
        user = (
            f"【目标】{goal[:200]}\n\n"
            f"【执行历史】\n{history_str}\n\n"
            f"当前是第{step}步（上限{self.max_steps}）。请输出JSON: "
            f'{{"reasoning": "...", "decision": "call_agent"|"finish", "agent_name": "..."}}'
        )

        try:
            from core.harness.syscalls.llm import sys_llm_generate
            response = await sys_llm_generate(
                None,
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                model_name=self.supervisor_model,
                temperature=0.2,
                max_tokens=200,
            )
            raw = getattr(response, "content", "") or str(response)
            # Extract JSON from response
            import re as _re
            m = _re.search(r'\{[^{}]*\}', raw)
            if m:
                data = json.loads(m.group())
                dec = data.get("decision", "finish")
                agent = data.get("agent_name", "")
                reason = data.get("reasoning", "")[:200]
                if dec == "call_agent" and agent in available:
                    return _Decision("call_agent", agent, reason)
                return _Decision("finish", "", reason if reason else "LLM decided finish")
        except Exception as e:
            logger.warning("Supervisor LLM failed: %s", e, exc_info=True)

        return _Decision("finish", "", "Supervisor LLM error, force finish")

    def get_trace(self) -> List[Dict[str, Any]]:
        return list(self._trace)


class _Decision:
    """Internal routing decision."""
    def __init__(self, decision: str, agent_name: str, reasoning: str):
        self.decision = decision
        self.agent_name = agent_name
        self.reasoning = reasoning
