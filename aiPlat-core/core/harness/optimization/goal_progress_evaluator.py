"""
GoalProgressEvaluator — 目标推进评估器 (Phase 39).

每完成一轮子目标后, 评估是否在接近总目标。
复用 UCB1 收敛检测逻辑 (来自 StrategySearchEngine)。

评估维度:
  - 子目标完成率 (completion_rate)
  - 收敛速度 (convergence_speed) — 正值为加速收敛, 负值为发散
  - 趋势判断 (trend) — converging / plateau / diverging
"""

from __future__ import annotations

import logging
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.harness.optimization.goal_generator import Goal

logger = logging.getLogger("aiplat.goal_progress_evaluator")


@dataclass
class ProgressReport:
    abstract_goal: str
    completed_count: int = 0
    total_count: int = 0
    completion_rate: float = 0.0
    convergence_speed: float = 0.0
    trend: str = "unknown"
    recommendation: str = "continue"
    detail: str = ""


class GoalProgressEvaluator:
    """评估子目标推行后是否在接近总目标。

    收敛检测逻辑:
      - 连续 plateau_threshold 轮无进展 → 触发 replan
      - convergence_speed 转负 → 触发 replan
      - 进度稳定推进 → continue
    """

    def __init__(self, *, plateau_threshold: int = 3):
        self._plateau_threshold = plateau_threshold
        self._plateau_counter = 0
        self._last_completion_rate: float = 0.0
        self._rate_history: List[float] = []
        self._evaluation_count = 0

    def evaluate(
        self,
        abstract_goal: str,
        completed_sub_goals: List[Goal],
        total_goals: int,
    ) -> ProgressReport:
        """评估进度并返回建议。

        Args:
            abstract_goal: 原始抽象目标文本
            completed_sub_goals: 已完成 (success=True) 的子目标列表
            total_goals: 本轮分解出的总子目标数
        """
        self._evaluation_count += 1
        completed = len(completed_sub_goals)
        rate = completed / max(total_goals, 1)

        self._rate_history.append(rate)
        if len(self._rate_history) > 10:
            self._rate_history = self._rate_history[-10:]

        delta = rate - self._last_completion_rate
        self._last_completion_rate = rate

        convergence = self._compute_convergence()

        if rate >= 1.0:
            trend = "completed"
            recommendation = "done"
            detail = f"全部 {total_goals} 个子目标已完成"
            self._plateau_counter = 0
        elif delta > 0.05:
            trend = "converging"
            recommendation = "continue"
            detail = f"进展良好，本轮完成 +{delta:.0%}"
            self._plateau_counter = 0
        elif delta > 0:
            trend = "converging"
            recommendation = "continue"
            detail = f"缓慢推进，+{delta:.0%}"
            self._plateau_counter = 0
        elif convergence < -0.1:
            self._plateau_counter += 1
            trend = "diverging"
            recommendation = "replan" if self._plateau_counter >= self._plateau_threshold else "continue"
            detail = (
                f"收敛速度转负 ({convergence:.2f})，连续停滞 {self._plateau_counter} 轮"
                if self._plateau_counter >= 2 else
                f"本轮无进展，继续观察"
            )
        else:
            self._plateau_counter += 1
            trend = "plateau"
            recommendation = "replan" if self._plateau_counter >= self._plateau_threshold else "continue"
            detail = (
                f"连续 {self._plateau_counter} 轮停滞"
                if self._plateau_counter >= 2 else
                "本轮无进展"
            )

        if self._plateau_counter >= self._plateau_threshold:
            recommendation = "replan"
            trend = "plateau"

        return ProgressReport(
            abstract_goal=abstract_goal,
            completed_count=completed,
            total_count=total_goals,
            completion_rate=rate,
            convergence_speed=convergence,
            trend=trend,
            recommendation=recommendation,
            detail=detail,
        )

    def _compute_convergence(self) -> float:
        """计算收敛速度。正 = 加速收敛, 负 = 发散。

        使用最近 3-5 个数据点的斜率 (简单线性回归)。
        """
        hist = self._rate_history
        if len(hist) < 3:
            return 0.0

        recent = hist[-min(len(hist), 5):]
        n = len(recent)
        if n < 2:
            return 0.0

        x_mean = (n - 1) / 2
        y_mean = sum(recent) / n

        numerator = sum(
            (i - x_mean) * (recent[i] - y_mean)
            for i in range(n)
        )
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return 0.0
        return numerator / denominator

    def should_replan(self, report: ProgressReport) -> bool:
        return report.recommendation == "replan"

    def reset(self) -> None:
        self._plateau_counter = 0
        self._last_completion_rate = 0.0
        self._rate_history.clear()

    def stats(self) -> Dict[str, Any]:
        return {
            "evaluation_count": self._evaluation_count,
            "plateau_counter": self._plateau_counter,
            "plateau_threshold": self._plateau_threshold,
            "last_completion_rate": self._last_completion_rate,
            "convergence": self._compute_convergence(),
        }


_goal_progress_evaluator: Optional[GoalProgressEvaluator] = None


def get_goal_progress_evaluator() -> GoalProgressEvaluator:
    global _goal_progress_evaluator
    if _goal_progress_evaluator is None:
        _goal_progress_evaluator = GoalProgressEvaluator()
    return _goal_progress_evaluator
