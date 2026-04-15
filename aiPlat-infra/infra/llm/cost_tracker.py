from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime


@dataclass
class CostRecord:
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float
    timestamp: datetime = field(default_factory=datetime.now)


class CostTracker:
    def __init__(self):
        self._records: Dict[str, CostRecord] = {}
        self._total_cost = 0.0
        self._total_tokens = 0

    def calculate(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """计算成本（便捷方法）"""
        prices = {
            "gpt-4": 0.03 / 1000,
            "gpt-3.5-turbo": 0.002 / 1000,
        }
        price = prices.get(model, 0.002 / 1000)
        cost = (input_tokens + output_tokens) * price
        self.record(model, input_tokens, output_tokens, cost)
        return cost

    def record(
        self, model: str, prompt_tokens: int, completion_tokens: int, cost: float
    ) -> None:
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
        return self._records.get(model)

    def get_total_cost(self) -> float:
        return self._total_cost

    def get_total_tokens(self) -> int:
        return self._total_tokens

    def get_cost_by_model(self) -> Dict[str, float]:
        return {m: r.cost for m, r in self._records.items()}

    def reset(self) -> None:
        self._records.clear()
        self._total_cost = 0.0
        self._total_tokens = 0

    def calculate_cost(
        self, model: str, prompt_tokens: int, completion_tokens: int
    ) -> float:
        PRICING = {
            "gpt-4": {"prompt": 0.03, "completion": 0.06},
            "gpt-4-turbo": {"prompt": 0.01, "completion": 0.03},
            "gpt-3.5-turbo": {"prompt": 0.001, "completion": 0.002},
            "text-embedding-3-small": {"prompt": 0.00002, "completion": 0},
        }

        pricing = PRICING.get(model, {"prompt": 0.01, "completion": 0.03})
        prompt_cost = (prompt_tokens / 1000000) * pricing["prompt"]
        completion_cost = (completion_tokens / 1000000) * pricing["completion"]
        return prompt_cost + completion_cost
