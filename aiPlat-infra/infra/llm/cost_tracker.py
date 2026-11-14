"""cost_tracker：模块接口。"""

from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime

# Default pricing is free (0) — callers MUST inject real pricing via
# CostTracker(pricing=...) or set_pricing(). This keeps infra config-driven
# and free of any hardcoded provider names (see CLAUDE.md §5.2/§5.3).
DEFAULT_PRICING: Dict[str, Dict[str, float]] = {}


@dataclass
class CostRecord:
    """CostRecord。"""
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float
    timestamp: datetime = field(default_factory=datetime.now)


class CostTracker:
    """CostTracker。"""
    def __init__(self, pricing: Optional[Dict[str, Dict[str, float]]] = None):
        """初始化。

        Args:
            pricing: pricing 参数。
        """
        self._records: Dict[str, CostRecord] = {}
        self._total_cost = 0.0
        self._total_tokens = 0
        self._pricing: Dict[str, Dict[str, float]] = dict(pricing or DEFAULT_PRICING)

    def set_pricing(self, pricing: Dict[str, Dict[str, float]]) -> None:
        """Replace the pricing table (USD per million tokens, {prompt, completion}).

        Args:
            pricing: pricing 参数。
        """
        self._pricing = dict(pricing or {})

    def calculate(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """计算成本（便捷方法）。

        Args:
            model: 模型名。
            input_tokens: input_tokens 参数。
            output_tokens: output_tokens 参数。
        """
        cost = self.calculate_cost(model, input_tokens, output_tokens)
        self.record(model, input_tokens, output_tokens, cost)
        return cost

    def record(
        self, model: str, prompt_tokens: int, completion_tokens: int, cost: float
    ) -> None:
        """record。

        Args:
            model: 模型名。
            prompt_tokens: prompt_tokens 参数。
            completion_tokens: completion_tokens 参数。
            cost: cost 参数。
        """
        total = prompt_tokens + completion_tokens
        self._records[model] = CostRecord(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            cost=cost,
        )
        self._total_cost += cost
        self._total_tokens += total

    def get_cost(self, model: str) -> Optional[CostRecord]:
        """获取 cost。

        Args:
            model: 模型名。
        """
        return self._records.get(model)

    def get_total_cost(self) -> float:
        """获取 total_cost。
        """
        return self._total_cost

    def get_total_tokens(self) -> int:
        """获取 total_tokens。
        """
        return self._total_tokens

    def get_cost_by_model(self) -> Dict[str, float]:
        """获取 cost_by_model。
        """
        return {m: r.cost for m, r in self._records.items()}

    def reset(self) -> None:
        """reset。
        """
        self._records.clear()
        self._total_cost = 0.0
        self._total_tokens = 0

    def calculate_cost(
        self, model: str, prompt_tokens: int, completion_tokens: int
    ) -> float:
        """Cost in USD from token counts and the injected pricing table.

        Args:
            model: 模型名。
            prompt_tokens: prompt_tokens 参数。
            completion_tokens: completion_tokens 参数。
        """
        pricing = self._pricing.get(model, {"prompt": 0.0, "completion": 0.0})
        prompt_cost = (prompt_tokens / 1000000.0) * pricing.get("prompt", 0.0)
        completion_cost = (completion_tokens / 1000000.0) * pricing.get("completion", 0.0)
        return prompt_cost + completion_cost
