"""Cost Budget Controller — per-run budget enforcement on top of the existing CostTracker.

The existing ``core.harness.optimization.cost_tracker.CostTracker`` (Phase 56)
is the single authority for token→USD cost estimation (pricing + aggregation).
This module adds a thin per-run budget enforcer (``over_budget`` /
``_should_downgrade``) without duplicating cost calculation or pricing.

Pricing source (single): ``config/model_pricing.yaml`` via ``get_cost_tracker()``.

This is a GENERIC engine capability — no business concepts.

Callers:
- ``core.harness.execution.pipeline_engine`` (record + over_budget check)
- ``core.api.core_facade`` canonical re-export
"""
from __future__ import annotations

from typing import Any, Dict, Optional

_COST_PRIORITIES = ("balanced", "minimize_cost", "maximize_quality")


def get_pricing() -> Dict[str, Dict[str, float]]:
    """Pricing table from the existing CostTracker (single source of truth)."""
    from core.harness.optimization.cost_tracker import get_cost_tracker
    return get_cost_tracker().get_pricing()


def cost_for(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Stateless USD cost for one call (existing CostTracker pricing).

    ``prompt_tokens`` map to the pricing ``input`` rate, ``completion_tokens``
    to the ``output`` rate (USD per million tokens).
    """
    p = get_pricing().get(model) or {"input": 0.0, "output": 0.0}
    return ((prompt_tokens / 1_000_000.0) * p.get("input", 0.0)
            + (completion_tokens / 1_000_000.0) * p.get("output", 0.0))


class CostBudgetController:
    """Per-run budget enforcer. Cost calc reuses the existing CostTracker pricing.

    ``max_cost_usd`` of 0 disables the budget. ``cost_priority`` controls
    downgrade behaviour when over budget (see :meth:`_should_downgrade`).
    """

    def __init__(
        self,
        pricing: Optional[Dict[str, Dict[str, float]]] = None,
        max_cost_usd: float = 0.0,
        cost_priority: str = "balanced",
    ):
        self._pricing: Dict[str, Dict[str, float]] = dict(
            pricing if pricing is not None else get_pricing()
        )
        self._budget = float(max_cost_usd or 0.0)
        self._priority = cost_priority if cost_priority in _COST_PRIORITIES else "balanced"
        self._cost_used = 0.0
        self._model_costs: Dict[str, float] = {}

    def cost_for(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """USD cost for one call, without accumulating."""
        p = self._pricing.get(model) or {"input": 0.0, "output": 0.0}
        return ((prompt_tokens / 1_000_000.0) * p.get("input", 0.0)
                + (completion_tokens / 1_000_000.0) * p.get("output", 0.0))

    def record(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Accumulate cost for one call and return the delta."""
        cost = self.cost_for(model, prompt_tokens, completion_tokens)
        self._cost_used += cost
        self._model_costs[model] = self._model_costs.get(model, 0.0) + cost
        return cost

    @property
    def cost_used(self) -> float:
        return self._cost_used

    @property
    def budget(self) -> float:
        return self._budget

    @property
    def cost_priority(self) -> str:
        return self._priority

    def over_budget(self) -> bool:
        return self._budget > 0.0 and self._cost_used >= self._budget

    def _should_downgrade(self) -> bool:
        """True when over budget and priority allows cost-minimizing.

        ``maximize_quality`` never downgrades; ``minimize_cost`` downgrades
        as soon as the budget is reached.
        """
        return self.over_budget() and self._priority != "maximize_quality"

    def snapshot(self) -> Dict[str, Any]:
        return {
            "cost_used_usd": round(self._cost_used, 6),
            "cost_budget_usd": self._budget,
            "cost_priority": self._priority,
            "model_costs": {k: round(v, 6) for k, v in self._model_costs.items()},
            "over_budget": self.over_budget(),
        }

