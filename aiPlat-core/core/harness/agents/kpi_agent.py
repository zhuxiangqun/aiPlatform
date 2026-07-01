"""
KPIAgent — Business owner's AI assistant.

Automatically tracks goal progress, alerts on deviation, and suggests strategy.
Wired into EvolutionEngine Step 12 (monthly) and BusinessGoals page (on load).

Classification: Semi-auto Human+Agent — Agent monitors, Human decides.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    level: str  # "ok" | "warning" | "critical"
    message: str
    suggested_action: str = ""


@dataclass
class StrategySuggestion:
    mode: str  # "speed" | "quality" | "guard" | "balanced"
    confidence: float  # 0-1
    reason: str = ""


class KPIAgent:
    """Auto-monitor business goals, alert on deviation, suggest strategy."""

    def __init__(self):
        self._deviation_threshold = float(
            __import__("os").getenv("AIPLAT_KPI_DEVIATION_THRESHOLD", "0.7"))

    async def monitor(self, goal_id: str) -> Alert:
        """Check goal progress; return warning if lagging.

        Called from: EvolutionEngine Step 12 (monthly), BusinessGoals page (on load)
        """
        try:
            from core.harness.finance.value_calculator import get_value_calculator
            calc = get_value_calculator()
            goal = calc.goal_tracker.get(goal_id)
            if not goal:
                return Alert(level="ok", message=f"Goal {goal_id} not found")

            if goal.achieved:
                return Alert(level="ok", message=f"✅ {goal.description} 已达成")

            if goal.progress_pct < self._deviation_threshold:
                ahead = goal.current_value > goal.target_value if goal.target_value > goal.baseline_value else goal.current_value < goal.target_value
                direction = "超过目标" if ahead else "落后于目标"
                return Alert(
                    level="warning" if goal.progress_pct > 0.3 else "critical",
                    message=f"⚠️ {goal.description} 进度仅 {goal.progress_pct:.0%}，{direction}",
                    suggested_action=(
                        "建议将对应 Agent 切换为提速模式" if not ahead
                        else "目标已达成，建议调高目标或关闭此 KPI"
                    ),
                )
            return Alert(level="ok", message=f"✅ {goal.description} 进度正常 ({goal.progress_pct:.0%})")
        except Exception as e:
            logger.debug("KPIAgent.monitor failed for %s: %s", goal_id, str(e)[:100])
            return Alert(level="ok", message="监控暂不可用")

    async def suggest_strategy(self, goal_id: str) -> Optional[StrategySuggestion]:
        """Analyze historical progress → recommend best strategy.

        Called from: BusinessGoals page (strategy suggestion card)
        """
        try:
            from core.harness.finance.value_calculator import get_value_calculator
            calc = get_value_calculator()
            goal = calc.goal_tracker.get(goal_id)
            if not goal or goal.achieved:
                return None

            if goal.progress_pct < self._deviation_threshold:
                return StrategySuggestion(
                    mode="speed", confidence=0.85,
                    reason=f"当前进度 {goal.progress_pct:.0%} < 目标 {self._deviation_threshold:.0%}，建议提速",
                )
            elif goal.progress_pct < 0.85:
                return StrategySuggestion(
                    mode="balanced", confidence=0.70,
                    reason=f"进度 {goal.progress_pct:.0%} 在安全范围内，保持当前策略",
                )
            return None
        except Exception as e:
            logger.debug("KPIAgent.suggest_strategy failed for %s: %s", goal_id, str(e)[:100])
            return None

    async def monitor_all(self) -> List[Alert]:
        """Check all business goals; return alerts for lagging ones."""
        try:
            from core.harness.finance.value_calculator import get_value_calculator
            calc = get_value_calculator()
            alerts = []
            for goal in calc.goal_tracker.get_all():
                alert = await self.monitor(goal.goal_id)
                if alert.level != "ok":
                    alerts.append(alert)
            return alerts
        except Exception:
            return []


_kpi_agent: Optional[KPIAgent] = None


def get_kpi_agent() -> KPIAgent:
    global _kpi_agent
    if _kpi_agent is None:
        _kpi_agent = KPIAgent()
    return _kpi_agent
