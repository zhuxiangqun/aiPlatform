"""
Phase 56: CostTracker — token-based cost estimation and aggregation.

Tracks cumulative token usage per agent and model, estimates USD cost
based on configurable pricing tiers. Exposed via self_healing diagnostics.

Pricing source: llm_profile.yaml tiers or environment variables.
"""

from __future__ import annotations

import logging
import os
import threading
from collections import defaultdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.cost_tracker")

def _load_default_pricing() -> Dict[str, Dict[str, float]]:
    """Load model pricing from config/model_pricing.yaml, fallback to inline defaults."""
    import os as _os, json as _json
    
    # Try YAML config first
    yaml_path = _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))),
        "config", "model_pricing.yaml"
    )
    try:
        import yaml as _yaml
        with open(yaml_path) as f:
            data = _yaml.safe_load(f)
        if isinstance(data, dict):
            return dict(data)
    except Exception:
        pass
    
    # Fallback inline defaults
    return {
        "deepseek-v4-pro":     {"input": 0.55, "output": 2.19},
        "deepseek-chat":       {"input": 0.14, "output": 0.28},
        "deepseek-coder":      {"input": 0.14, "output": 0.28},
        "qwen2.5-coder:7b":    {"input": 0.0,  "output": 0.0},
        "qwen2.5:3b":          {"input": 0.0,  "output": 0.0},
        "gpt-4o":              {"input": 2.50, "output": 10.00},
        "gpt-4o-mini":         {"input": 0.15, "output": 0.60},
        "claude-3.5-sonnet":   {"input": 3.00, "output": 15.00},
    }


_DEFAULT_PRICING = _load_default_pricing()


class CostTracker:
    """Tracks and estimates token usage costs.

    Thread-safe. Usage:
        tracker = get_cost_tracker()
        tracker.record("deepseek-v4-pro", input_tokens=500, output_tokens=200)
        tracker.record("qwen2.5-coder:7b", input_tokens=1000, output_tokens=500)
        print(tracker.stats())
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._usage: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # { model: {"input_tokens": N, "output_tokens": M, "requests": K} }
        self._tenant_usage: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(int)))
        # { tenant: { model: {"input_tokens": N, "output_tokens": M, "requests": K} } }
        self._pricing = dict(_DEFAULT_PRICING)
        self._load_pricing_env()

    def _load_pricing_env(self):
        try:
            import json
            env_data = os.getenv("AIPLAT_MODEL_PRICING", "")  # noqa: env-legacy — pricing config, not model name
            if env_data:
                custom = json.loads(env_data)
                self._pricing.update(custom)
        except Exception:
            pass

    def record(self, model: str, input_tokens: int = 0, output_tokens: int = 0,
               tenant_id: str = "default") -> None:
        if not model:
            return
        with self._lock:
            self._usage[model]["input_tokens"] += input_tokens
            self._usage[model]["output_tokens"] += output_tokens
            self._usage[model]["requests"] += 1
            tu = self._tenant_usage[tenant_id][model]
            tu["input_tokens"] += input_tokens
            tu["output_tokens"] += output_tokens
            tu["requests"] += 1

    def cost_for_model(self, model: str) -> float:
        pricing = self._pricing.get(model, {"input": 0.0, "output": 0.0})
        u = self._usage[model]
        input_cost = u["input_tokens"] / 1_000_000 * pricing["input"]
        output_cost = u["output_tokens"] / 1_000_000 * pricing["output"]
        return round(input_cost + output_cost, 4)

    def total_cost(self) -> float:
        return round(sum(self.cost_for_model(m) for m in self._usage), 4)

    def total_tokens(self) -> int:
        return sum(u["input_tokens"] + u["output_tokens"] for u in self._usage.values())

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            per_model = {}
            for model, u in sorted(self._usage.items()):
                per_model[model] = {
                    "requests": u["requests"],
                    "input_tokens": u["input_tokens"],
                    "output_tokens": u["output_tokens"],
                    "total_tokens": u["input_tokens"] + u["output_tokens"],
                    "cost_usd": self.cost_for_model(model),
                }
            return {
                "total_requests": sum(u["requests"] for u in self._usage.values()),
                "total_tokens": self.total_tokens(),
                "total_cost_usd": self.total_cost(),
                "per_model": per_model,
            }

    def stats_by_tenant(self) -> Dict[str, Any]:
        """Per-tenant cost breakdown for enterprise reporting."""
        with self._lock:
            tenants = {}
            for tenant, models in self._tenant_usage.items():
                tenant_cost = 0.0
                tenant_tokens = 0
                for model, u in models.items():
                    pricing = self._pricing.get(model, {"input": 0.0, "output": 0.0})
                    tc = (u["input_tokens"] / 1_000_000 * pricing["input"] +
                          u["output_tokens"] / 1_000_000 * pricing["output"])
                    tenant_cost += tc
                    tenant_tokens += u["input_tokens"] + u["output_tokens"]
                tenants[tenant] = {
                    "total_tokens": tenant_tokens,
                    "total_cost_usd": round(tenant_cost, 4),
                    "requests": sum(u["requests"] for u in models.values()),
                }
            return {"tenants": tenants, "tenant_count": len(tenants)}


_tracker: Optional[CostTracker] = None


def get_cost_tracker() -> CostTracker:
    global _tracker
    if _tracker is None:
        _tracker = CostTracker()
    return _tracker
