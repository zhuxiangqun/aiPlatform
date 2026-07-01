"""
StrategyAgent — Tech lead's AI assistant.

Auto-adjusts agent parameters within safe limits, responds to realtime anomalies.
Wired into GoalAwareRouter (auto-adjust) and ToolDriftDetector (anomaly response).

Classification: Semi-auto Human+Agent — Agent auto-adjusts, Human approves big changes.

Safe adjustment scope (Agent can auto-apply):
  - max_steps (10-20)
  - bypass_approval_known (true/false)
  - force_reflection (true/false)

Unsafe scope (requires Human approval):
  - model switch
  - circuit threshold change
  - immune_level change
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AdjustResult:
    adjustments: List[Dict[str, Any]] = field(default_factory=list)
    requires_approval: bool = False


class StrategyAgent:
    """Auto-manage agent parameters within safe boundaries."""

    SAFE_PARAMS = {"max_steps", "bypass_approval_known", "force_reflection"}
    UNSAFE_PARAMS = {"model_name", "circuit_threshold", "immune_level"}

    async def auto_adjust(self, goal_id: str) -> AdjustResult:
        """Read goal status → suggest safe parameter adjustments.

        Called from: GoalAwareRouter.adjust() — merged into routing strategy.
        """
        result = AdjustResult()
        try:
            from core.harness.finance.value_calculator import get_value_calculator
            calc = get_value_calculator()
            goal = calc.goal_tracker.get(goal_id)
            if not goal:
                return result

            if goal.progress_pct < 0.7:
                result.adjustments.append({
                    "param": "max_steps", "from": 15, "to": 10,
                    "reason": f"目标 {goal.description} 进度 {goal.progress_pct:.0%}，减少冗余步骤",
                    "safe": True,
                })
                result.adjustments.append({
                    "param": "bypass_approval_known", "from": False, "to": True,
                    "reason": "跳过已知任务的审批环节以提速",
                    "safe": True,
                })

            if goal.progress_pct < 0.5:
                result.adjustments.append({
                    "param": "force_reflection", "from": True, "to": False,
                    "reason": "严重落后时关闭反思以加快执行",
                    "safe": True,
                })
                result.adjustments.append({
                    "param": "model_name", "from": "current", "to": "gpt-4o",
                    "reason": "升级到强模型以突破质量瓶颈",
                    "safe": False,  # requires approval
                })
                result.requires_approval = True
        except Exception:
            pass
        return result

    async def handle_anomaly(self, alert_type: str, tool_name: str) -> AdjustResult:
        """Respond to realtime anomaly alerts with auto-adjustments.

        Called from: ToolDriftDetector._alert() → layer 2 glue.
        """
        result = AdjustResult()
        if alert_type == "cascade_failure":
            result.adjustments.append({
                "param": "bypass_approval_known", "from": True, "to": False,
                "reason": f"级联失败: {tool_name}，关闭自动审批以加强人工监管",
                "safe": True,
            })
        elif alert_type == "outlier_latency":
            result.adjustments.append({
                "param": "max_steps", "from": 15, "to": 8,
                "reason": f"延迟异常: {tool_name}，减少单任务执行深度",
                "safe": True,
            })
        elif alert_type == "redundant_call":
            result.adjustments.append({
                "param": "max_steps", "from": 15, "to": 12,
                "reason": f"冗余调用: {tool_name}，适度压缩步骤数",
                "safe": True,
            })
        return result


_strategy_agent: Optional[StrategyAgent] = None


def get_strategy_agent() -> StrategyAgent:
    global _strategy_agent
    if _strategy_agent is None:
        _strategy_agent = StrategyAgent()
    return _strategy_agent
