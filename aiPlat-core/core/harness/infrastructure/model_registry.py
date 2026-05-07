"""
Model Registry — unified model metadata for dynamic routing.

Models are configured via AIPLAT_MODELS env var (JSON array) or default.yaml.
Each entry: {name, provider, api_key_env, base_url, capabilities, cost_per_1k_tokens}

Per §5.1 (infra), models are discovered from infra and injected here by the
service layer. This module defines the contract that core uses.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ModelEntry:
    """Metadata for one model deployment."""
    name: str                        # "gpt-4o" or "deepseek-reasoner"
    provider: str                    # "openai", "deepseek", "anthropic", "local"
    api_key: str = ""
    api_key_env: str = ""            # env var name for the API key
    base_url: str = ""
    enabled: bool = True
    capabilities: List[str] = field(default_factory=lambda: ["chat"])
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0

    # Runtime state (populated by ModelRouter)
    failure_count: int = 0
    total_calls: int = 0
    total_success: int = 0
    cooldown_until: float = 0.0      # timestamp
    last_latency_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.total_success / self.total_calls

    @property
    def in_cooldown(self) -> bool:
        import time
        return time.time() < self.cooldown_until

    @property
    def api_key_resolved(self) -> str:
        return self.api_key or os.getenv(self.api_key_env, "")


class ModelRegistry:
    """Unified model registry queried by ModelRouter."""

    def __init__(self):
        self._models: Dict[str, List[ModelEntry]] = {}  # model_name → [deployment, ...]
        self._purpose_map: Dict[str, str] = {}           # purpose → model_name
        self._load_defaults()
        self._load_purpose_map()

    def _load_purpose_map(self):
        """Read AiPlat-specific per-purpose model defaults from env."""
        purposes = [
            ("default", "AIPLAT_LLM_MODEL"),
            ("document", "AIPLAT_DOC_LLM_MODEL"),
            ("agent", "AIPLAT_AGENT_MODEL"),
        ]
        for purpose, env_var in purposes:
            model = os.getenv(env_var, "").strip()
            if model:
                self._purpose_map[purpose] = model

    def get_default_for_purpose(self, purpose: str = "default") -> str:
        """Get the default model for a specific purpose.

        Examples:
            registry.get_default_for_purpose("agent")     → "deepseek-reasoner"
            registry.get_default_for_purpose("document")  → "deepseek-chat"
            registry.get_default_for_purpose("default")   → "deepseek-chat"
        """
        return self._purpose_map.get(purpose) or self._purpose_map.get("default", "deepseek-chat")

    def _load_defaults(self):
        """Load models from AIPLAT_MODELS env or hardcoded defaults."""
        models_json = os.getenv("AIPLAT_MODELS", "")
        if models_json:
            try:
                data = json.loads(models_json)
                for entry in data:
                    m = ModelEntry(
                        name=entry.get("name", ""),
                        provider=entry.get("provider", ""),
                        api_key=entry.get("api_key", ""),
                        api_key_env=entry.get("api_key_env", ""),
                        base_url=entry.get("base_url", ""),
                        enabled=entry.get("enabled", True),
                        capabilities=entry.get("capabilities", ["chat"]),
                        cost_per_1k_input=entry.get("cost_per_1k_input", 0.0),
                        cost_per_1k_output=entry.get("cost_per_1k_output", 0.0),
                    )
                    if m.name and m.enabled:
                        self._models.setdefault(m.name, []).append(m)
                return
            except json.JSONDecodeError:
                pass

        # Fallback defaults
        deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
        if deepseek_key:
            self.register(ModelEntry(
                name="deepseek-reasoner", provider="deepseek",
                api_key_env="DEEPSEEK_API_KEY", base_url="https://api.deepseek.com",
                capabilities=["chat", "reasoning"],
                cost_per_1k_input=0.00055, cost_per_1k_output=0.00219,
            ))
            self.register(ModelEntry(
                name="deepseek-chat", provider="deepseek",
                api_key_env="DEEPSEEK_API_KEY", base_url="https://api.deepseek.com",
                cost_per_1k_input=0.00027, cost_per_1k_output=0.00110,
            ))

        openai_key = os.getenv("OPENAI_API_KEY", "")
        if openai_key:
            self.register(ModelEntry(
                name="gpt-4o", provider="openai",
                api_key_env="OPENAI_API_KEY",
                capabilities=["chat", "reasoning", "function_call"],
                cost_per_1k_input=0.0025, cost_per_1k_output=0.010,
            ))
            self.register(ModelEntry(
                name="gpt-4o-mini", provider="openai",
                api_key_env="OPENAI_API_KEY",
                cost_per_1k_input=0.00015, cost_per_1k_output=0.0006,
            ))

    def register(self, entry: ModelEntry) -> None:
        if entry.name not in self._models:
            self._models[entry.name] = []
        self._models[entry.name].append(entry)

    def get_candidates(self, model_name: str) -> List[ModelEntry]:
        """Get all healthy deployments for a model name (excluding cooldown)."""
        entries = self._models.get(model_name, [])
        return [e for e in entries if e.enabled and not e.in_cooldown]

    def get_cheaper_alternative(self, model_name: str) -> Optional[ModelEntry]:
        """Find a cheaper model in the same provider family."""
        entries = self._models.get(model_name, [])
        if not entries:
            return None
        # Look for entries from same provider with lower cost
        provider = entries[0].provider
        for name, models in self._models.items():
            for m in models:
                if m.provider == provider and m.cost_per_1k_input < entries[0].cost_per_1k_input:
                    return m
        return None

    def all_models(self) -> List[str]:
        return sorted(self._models.keys())


# Global singleton
_model_registry: Optional[ModelRegistry] = None


def get_model_registry() -> ModelRegistry:
    global _model_registry
    if _model_registry is None:
        _model_registry = ModelRegistry()
    return _model_registry
