"""
Pipeline Conditional Routing — semantic branch conditions for PipelineGraph edges.

Inspired by TradingAgents' ConditionalLogic (debate convergence, risk threshold checks).
Extensible: register new conditions via CONDITION_REGISTRY.

Caller: PipelineGraph.compile() uses these to wire conditional edges in LangGraph.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from core.schemas_builder import PipelineStageConfig
from core.harness.execution.pipeline_engine import PipelineState


# disposition: internal helper — resolved via CONDITION_REGISTRY in same module, wired to PipelineGraph.get_condition()
class PipelineCondition:
    """Semantic routing conditions for pipeline graph edges."""

    @staticmethod
    def debate_converged(state: PipelineState) -> str:
        """Route based on debate convergence state.
        
        Returns 'done' if debate has converged, 'continue' otherwise.
        Used as a conditional edge between debate nodes and the manager.
        """
        debate = state.get("_debate_state") or {}
        if isinstance(debate, dict) and debate.get("converged"):
            return "done"
        rounds = int(debate.get("rounds", 0) if isinstance(debate, dict) else 0)
        max_rds = int(debate.get("max_rounds", 8) if isinstance(debate, dict) else 8)
        if rounds >= max_rds:
            return "done"
        return "continue"

    @staticmethod
    def risk_threshold(state: PipelineState, *, key: str = "_risk_score", threshold: float = 5.0) -> str:
        """Route based on risk score threshold.
        
        Returns 'high_risk' if score >= threshold, 'low_risk' otherwise.
        """
        score = float(state.get(key, 0) or 0)
        return "high_risk" if score >= threshold else "low_risk"

    @staticmethod
    def phase_check(state: PipelineState) -> str:
        """Route based on current pipeline phase (enum-driven, not string matching).
        
        Returns: 'done' | 'failed' | 'paused' | 'executing'
        """
        from core.schemas_builder import BuilderSessionPhase
        phase = str(state.get("phase", BuilderSessionPhase.executing.value))
        if phase == BuilderSessionPhase.done.value:
            return "done"
        if phase == BuilderSessionPhase.failed.value:
            return "failed"
        if phase == BuilderSessionPhase.paused.value:
            return "paused"
        return "executing"

    @staticmethod
    def stage_completed(state: PipelineState, stage_id: str) -> str:
        """Check if a specific stage has been completed.
        
        Returns: 'completed' | 'not_completed'
        """
        done_key = f"_stage_{stage_id}_done"
        return "completed" if state.get(done_key) else "not_completed"

    @staticmethod
    def passes_threshold(state: PipelineState, *, metric: str = "pass_rate", threshold: float = 0.8) -> str:
        """Generic threshold check on a numeric state metric.
        
        Returns: 'pass' | 'fail'
        """
        value = float(state.get(metric, 0) or 0)
        return "pass" if value >= threshold else "fail"


# Registry for custom conditions injected by platform/app layers
CONDITION_REGISTRY: Dict[str, Callable] = {
    "debate_converged": PipelineCondition.debate_converged,
    "risk_threshold": PipelineCondition.risk_threshold,
    "phase_check": PipelineCondition.phase_check,
    "stage_completed": PipelineCondition.stage_completed,
    "passes_threshold": PipelineCondition.passes_threshold,
}


__all__ = [
    "PipelineCondition",
    "CONDITION_REGISTRY",
]
