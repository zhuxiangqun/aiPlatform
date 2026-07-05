"""
Phase 29: StrategySearchEngine — UCB1 multi-arm bandit for self-healing strategy selection.

Replaces the greedy "best known" routing in Phase 26 with a theoretically-grounded
exploration-exploitation balancing algorithm.

Core insight: each (error_type) is a multi-arm bandit problem with 4 arms (strategies).
UCB1 provides guaranteed sub-linear regret — it converges to the optimal strategy
while minimizing total regret (unsuccessful attempts).

Algorithm:
  For each strategy i:
    Q_i = successes_i / attempts_i          (exploitation: historical success rate)
    U_i = sqrt(2 * ln(T+1) / (attempts_i+1))  (exploration: optimism bound)
    score_i = Q_i + U_i
  Select: argmax_i score_i

Convergence: when the best strategy's upper bound exceeds all others' upper bounds,
exploration is no longer needed. MAX_EXPLORE (50) provides a hard ceiling.

Integration: replaces _resolve_best_strategy() → one-line change in pipeline_engine.py.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("aiplat.search_engine")

MAX_EXPLORE = 50  # hard cap: stop exploring after this many total attempts
CONVERGE_WINDOW = 5  # consecutive selections of same strategy → converge
EPSILON = 1e-9  # avoid division by zero in convergence check


@dataclass
class UCB1Arm:
    """One strategy arm in the bandit."""
    strategy_name: str
    attempts: int = 0
    successes: int = 0

    @property
    def q(self) -> float:
        """Exploitation term: historical success rate."""
        return self.successes / self.attempts if self.attempts > 0 else 0.0

    def ucb_score(self, total_attempts: int) -> float:
        """UCB1 upper confidence bound."""
        if self.attempts == 0:
            return 0.0  # cold-start: don't select untried strategies
        exploitation = self.q
        exploration = math.sqrt(2.0 * math.log(total_attempts + 1) / self.attempts)
        return exploitation + exploration

    def upper_bound(self, total_attempts: int) -> float:
        """Upper bound for convergence check (includes exploration bonus)."""
        if self.attempts == 0:
            return float("inf")  # avoid converging before all tried
        return self.q + math.sqrt(2.0 * math.log(total_attempts + 1) / (self.attempts + 1))


class StrategySearchEngine:
    """UCB1-based strategy selector for self-healing.

    Usage:
        engine = StrategySearchEngine(tracker)
        best = engine.select_best("timeout")
        # → "compress_retry" (exploitation) or "rotate_credential" (exploration)

        converged, best = engine.is_converged("timeout")
        # → (False, None)  during exploration
        # → (True, "compress_retry")  after convergence
    """

    def __init__(self, tracker):
        self._tracker = tracker
        self._converged: Dict[str, str] = {}  # error_type → frozen best_strategy
        self._consecutive: Dict[str, Tuple[str, int]] = {}  # (last_selected, count)

    def _get_arms(self, error_type: str) -> List[UCB1Arm]:
        """Build UCB1 arms from tracker data."""
        arms = []
        for strategy_name in self._tracker.ALL_STRATEGIES:
            rec = self._tracker._get_or_create(error_type, strategy_name)
            arms.append(UCB1Arm(
                strategy_name=strategy_name,
                attempts=rec.attempts,
                successes=rec.successes,
            ))
        return arms

    def select_best(self, error_type: str) -> Optional[str]:
        """Select best strategy using UCB1. Returns None if cold start."""
        # Check if already converged
        if error_type in self._converged:
            return self._converged[error_type]

        arms = self._get_arms(error_type)
        total = sum(a.attempts for a in arms)

        # Cold start: ensure every arm has at least 1 attempt
        if any(a.attempts == 0 for a in arms):
            # Let Phase 26 cold-start exploration handle this
            return None

        # Hard cap: force convergence
        if total >= MAX_EXPLORE:
            best_arm = max(arms, key=lambda a: a.q)
            self._converged[error_type] = best_arm.strategy_name
            logger.info(
                "[ucb1] forced converge: %s → %s (total=%d q=%.2f)",
                error_type, best_arm.strategy_name, total, best_arm.q,
            )
            return best_arm.strategy_name

        # UCB1 selection
        scores = [(a.strategy_name, a.ucb_score(total)) for a in arms]
        scores.sort(key=lambda x: -x[1])

        selected_name, selected_score = scores[0]
        runner_up_score = scores[1][1] if len(scores) > 1 else 0.0

        # Track consecutive selections for convergence
        prev = self._consecutive.get(error_type)
        if prev and prev[0] == selected_name:
            count = prev[1] + 1
        else:
            count = 1
        self._consecutive[error_type] = (selected_name, count)

        # Soft convergence: same strategy selected CONVERGE_WINDOW times in a row
        if count >= CONVERGE_WINDOW and total >= CONVERGE_WINDOW * 2:
            self._converged[error_type] = selected_name
            logger.info(
                "[ucb1] soft converge: %s → %s (%d consecutive, total=%d score=%.3f)",
                error_type, selected_name, count, total, selected_score,
            )
            return selected_name

        logger.debug(
            "[ucb1] select: %s → %s (score=%.3f vs runner-up=%.3f, total=%d, consecutive=%d)",
            error_type, selected_name, selected_score, runner_up_score, total, count,
        )
        return selected_name

    def is_converged(self, error_type: str) -> Tuple[bool, Optional[str]]:
        """Check if a strategy has converged for this error type."""
        if error_type in self._converged:
            return True, self._converged[error_type]

        arms = self._get_arms(error_type)
        total = sum(a.attempts for a in arms)

        # Not enough data
        if total < 3:
            return False, None

        # Compute upper bounds
        best_arm = max(arms, key=lambda a: a.q)
        best_upper = best_arm.upper_bound(total)
        other_uppers = [
            a.upper_bound(total) for a in arms
            if a.strategy_name != best_arm.strategy_name
        ]

        # Convergence: best upper bound exceeds all others
        if other_uppers and best_upper > max(other_uppers) - EPSILON:
            # Converged if best_upper dominates AND total is sufficient
            if total >= CONVERGE_WINDOW * 2:
                self._converged[error_type] = best_arm.strategy_name
                return True, best_arm.strategy_name

        return False, None

    def reset(self, error_type: str = "") -> None:
        """Reset convergence state (e.g., after pipeline config change)."""
        if error_type:
            self._converged.pop(error_type, None)
            self._consecutive.pop(error_type, None)
        else:
            self._converged.clear()
            self._consecutive.clear()

    def get_converged_count(self) -> int:
        return len(self._converged)

    def stats(self) -> Dict[str, Any]:
        """Search engine statistics."""
        return {
            "converged_count": len(self._converged),
            "converged": dict(self._converged),
            "consecutive": {k: v[1] for k, v in self._consecutive.items()},
            "max_explore": MAX_EXPLORE,
            "converge_window": CONVERGE_WINDOW,
        }

    def explain_decision(self, error_type: str) -> Dict[str, Any]:
        """Phase 54: Explain why a specific strategy was selected (model interpretability).

        Returns per-strategy breakdown: Q(exploitation), U(exploration), UCB score.
        """
        arms = self._get_arms(error_type)
        total = sum(a.attempts for a in arms)
        scoring = []
        for a in arms:
            ucb = a.ucb_score(total) if a.attempts > 0 else 0.0
            scoring.append({
                "strategy": a.strategy_name,
                "attempts": a.attempts,
                "successes": a.successes,
                "success_rate": round(a.q, 3),
                "exploration_term": round(ucb - a.q, 3) if a.attempts > 0 else 0.0,
                "ucb_score": round(ucb, 3),
            })
        scoring.sort(key=lambda x: -x["ucb_score"])
        return {
            "error_type": error_type,
            "total_attempts": total,
            "converged": error_type in self._converged,
            "frozen_strategy": self._converged.get(error_type),
            "scoring": scoring,
            "selection_reason": (
                f"Converged to {self._converged[error_type]}" if error_type in self._converged
                else f"UCB1 selected {scoring[0]['strategy']} (score={scoring[0]['ucb_score']:.3f})"
            ),
        }


# ── Singleton ──

_engine: Optional[StrategySearchEngine] = None


def get_search_engine() -> StrategySearchEngine:
    """Get or create the process-wide search engine."""
    global _engine
    if _engine is None:
        from core.harness.optimization.strategy_tracker import get_strategy_tracker
        _engine = StrategySearchEngine(get_strategy_tracker())
    return _engine
