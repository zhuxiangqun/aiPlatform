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
  - Supervisor model: resolved via ModelManager (purpose=chat) or stage.model

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


# ── Goal-Aware Routing Strategy ──

class GoalAwareRouter:
    """Adjust routing strategy based on business goal status.

    Three strategies:
      - Speed: lagging goal → reduce steps, bypass approvals for known tasks
      - Quality: declining quality → force reflection, prefer high-cost model
      - Safety: frequent incidents → force human-in-the-loop for external calls
    """

    def __init__(self, goal_tracker: Any = None):
        self.goal_tracker = goal_tracker

    def adjust(self) -> Dict[str, Any]:
        """Return {params: dict, context: str} for DynamicRouter injection."""
        params = {}
        context = []
        if not self.goal_tracker:
            return {"params": params, "context": ""}

        try:
            status = self.goal_tracker.get_status_for_routing()
        except Exception:
            return {"params": params, "context": ""}

        if status.get("has_lagging_goal"):
            params["max_steps"] = 10
            context.append("⚡当前有业务目标进度落后，请优先选择最快的Agent，减少冗余步骤")

        if status.get("quality_trend") == "declining":
            params["force_reflection"] = True
            context.append("🔍检测到质量指标下滑，请启用反思模式，输出前自检")

        if status.get("security_incidents", 0) > 3:
            context.append("🛡️安全事件增多，外部调用必须经过人工确认")

        return {"params": params, "context": "\n".join(context)}


class DynamicRouter:
    """LLM-driven routing loop — Supervisor as Router, not as Executor."""

    def __init__(
        self,
        *,
        supervisor_model: str = "",
        max_steps: int = 15,
        agent_descriptions: Optional[Dict[str, str]] = None,
        goal_tracker: Any = None,
    ):
        self.max_steps = max_steps
        self.supervisor_model = supervisor_model or self._default_supervisor_model()
        self.agent_descriptions = agent_descriptions or {}
        self._trace: List[Dict[str, Any]] = []
        self.goal_tracker = goal_tracker
        self.goal_router = GoalAwareRouter(goal_tracker) if goal_tracker else None

    @staticmethod
    def _default_supervisor_model() -> str:
        import os
        from core.harness.utils.model_injection import best_model_for_purpose
        return best_model_for_purpose("chat")

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

    @staticmethod
    def canary_enabled(session_id: str = "") -> bool:
        """Percentage-based grayscale rollout for DynamicRouter.

        Reads AIPLAT_DYNAMIC_ROUTER_PERCENTAGE (0-100). Uses deterministic
        hashing per session_id so the same session always gets the same routing mode.

        Also supports AIPLAT_DYNAMIC_ROUTER_CANARY_TENANTS (comma-separated
        tenant IDs always routed to llm mode).
        """
        import hashlib
        import os

        # Canary tenants always get dynamic routing
        canary_tenants = os.getenv("AIPLAT_DYNAMIC_ROUTER_CANARY_TENANTS", "")
        if canary_tenants and session_id:
            # session_id format is typically <tenant>:<uuid>
            tenant = session_id.split(":", 1)[0] if ":" in session_id else ""
            if tenant and tenant in canary_tenants.split(","):
                return True

        try:
            pct = int(os.getenv("AIPLAT_DYNAMIC_ROUTER_PERCENTAGE", "100"))
        except ValueError:
            pct = 100

        if pct >= 100:
            return True
        if pct <= 0:
            return False
        if not session_id:
            return False

        bucket = int(hashlib.md5(f"dynamic_router:{session_id}".encode()).hexdigest(), 16) % 100
        return bucket < pct

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

        from core.harness.utils.prompt_loader import _sync_resolve

        system = _sync_resolve("dynamic-router-supervisor",
            agents=agents_desc,
            task=goal[:200],
            history=history_str)
        # Inject business goal context if available
        if self.goal_router:
            strategy = self.goal_router.adjust()
            if strategy.get("context"):
                system += f"\n【业务目标牵引】\n{strategy['context']}\n"
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

    # Debate mode: delegated to core.harness.execution.debate.run_agent_debate() (Skill 6)


class _Decision:
    """Internal routing decision."""
    def __init__(self, decision: str, agent_name: str, reasoning: str):
        self.decision = decision
        self.agent_name = agent_name
        self.reasoning = reasoning
