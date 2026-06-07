"""
Model Router — task-aware dynamic model selection with failure fallback.

Model metadata comes from aiPlat-infra's ModelManager (unique source of truth).
Runtime state (failure tracking, cooldown) is managed here.
"""

from __future__ import annotations

import os
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ModelEntry:
    """Runtime wrapper around infra model, with failure/cooldown tracking."""
    name: str
    provider: str = ""
    api_key: str = ""
    api_key_env: str = ""
    base_url: str = ""
    enabled: bool = True
    capabilities: List[str] = field(default_factory=lambda: ["chat"])
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0

    # Runtime state
    failure_count: int = 0
    total_calls: int = 0
    total_success: int = 0
    cooldown_until: float = 0.0
    last_latency_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.total_success / self.total_calls

    @property
    def in_cooldown(self) -> bool:
        return self.cooldown_until > time.time()


def _resolve_infra():
    """Get infra ModelManager (with fallback)."""
    try:
        from infra.management.model.manager import ModelManager
        return ModelManager()
    except Exception:
        return None


def _infra_to_entry(mi) -> ModelEntry:
    """Convert infra ModelInfo to core ModelEntry (runtime state)."""
    import os as _os
    cfg = mi.config if mi.config else type('cfg', (), {'api_key_env': '', 'base_url': ''})()
    api_key_env = getattr(cfg, 'api_key_env', '') or ""
    # Resolve API key from env var
    if not api_key_env:
        for env_name in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            if _os.getenv(env_name, "").strip():
                api_key_env = env_name
                break
    return ModelEntry(
        name=mi.name,
        provider=mi.provider or "",
        api_key=_os.getenv(api_key_env, "") or "",
        api_key_env=api_key_env,
        base_url=getattr(cfg, 'base_url', '') or "",
        enabled=getattr(mi, 'enabled', True),
        capabilities=getattr(mi, 'capabilities', []) or ["chat"],
    )


# ── Router configuration ──────────────────────────────────────────────

@dataclass
class RouterConfig:
    max_consecutive_failures: int = 3
    cooldown_duration_seconds: float = 30.0
    health_check_interval_seconds: float = 60.0
    prefer_cheapest: bool = False
    try_cheaper_on_rate_limit: bool = True


# ── Router ────────────────────────────────────────────────────────────

class ModelRouter:
    """Task-aware model selector with failure fallback and persistence."""

    def __init__(self, config: Optional[RouterConfig] = None):
        self._config = config or RouterConfig()
        self._mgr = _resolve_infra()
        self._entries: Dict[str, ModelEntry] = {}  # Runtime state per model
        self._fallback_history: Dict[str, List[str]] = {}
        self._load_persisted_state()

    async def select(
        self,
        model_name: str = "",
        task_purpose: str = "",
        task_complexity: str = "medium",
        task_budget: Optional[float] = None,
    ) -> Optional[ModelEntry]:
        """Select the best model for a task.

        Resolution order:
          1. model_name given → use directly
          2. task_purpose given → resolve via infra ModelManager.get_default_model()
          3. Fallback to default purpose
        """
        # Resolve model name
        if not model_name and task_purpose and self._mgr:
            model_name = self._mgr.get_default_model(task_purpose)
        if not model_name and self._mgr:
            model_name = self._mgr.get_default_model("default")
        if not model_name:
            return None

        # Get or create runtime entry
        entry = self._get_or_create_entry(model_name)
        if not entry.enabled or entry.in_cooldown:
            return None

        # Prefer cheaper for low-complexity tasks
        if task_complexity == "low" and self._config.prefer_cheapest:
            alt = self._get_cheaper_alternative(model_name)
            if alt:
                return alt

        # Exclude already-failed deployments for this call
        tried = set(self._fallback_history.get(model_name, []))
        if entry.name in tried:
            # Try to find another entry from same provider
            for name, e in self._entries.items():
                if e.provider == entry.provider and name not in tried:
                    return e

        return entry

    def _get_or_create_entry(self, model_name: str) -> Optional[ModelEntry]:
        """Get or create a ModelEntry, synced from infra."""
        # Always refresh from infra to pick up env var changes
        if self._mgr:
            for mi_id, mi in self._mgr._models.items():
                if mi.name == model_name or mi_id.endswith(f":{model_name}"):
                    entry = _infra_to_entry(mi)
                    self._entries[model_name] = entry
                    return entry
        return None

    def _get_cheaper_alternative(self, model_name: str) -> Optional[ModelEntry]:
        if model_name not in self._entries:
            return None
        entry = self._entries[model_name]
        for name, e in self._entries.items():
            if e.provider == entry.provider and e.cost_per_1k_input < entry.cost_per_1k_input:
                return e
        return None

    def mark_success(self, model_name: str, entry: ModelEntry) -> None:
        entry.total_calls += 1
        entry.total_success += 1
        entry.failure_count = 0
        self._fallback_history.pop(model_name, None)
        self._persist_state()

    def mark_failure(self, model_name: str, entry: ModelEntry) -> None:
        entry.total_calls += 1
        entry.failure_count += 1
        if entry.failure_count >= self._config.max_consecutive_failures:
            entry.cooldown_until = time.time() + self._config.cooldown_duration_seconds
            entry.failure_count = 0
        self._fallback_history.setdefault(model_name, []).append(entry.name)
        self._persist_state()

    def clear_fallback_history(self, model_name: str) -> None:
        self._fallback_history.pop(model_name, None)

    # ── Persistence ──

    def _state_path(self) -> str:
        home = os.getenv("AIPLAT_HOME", str(os.path.expanduser("~/.aiplat")))
        return os.path.join(home, "model_router_state.json")

    def _persist_state(self) -> None:
        try:
            import json
            data = {}
            for name, e in self._entries.items():
                data[name] = {
                    "failure_count": e.failure_count,
                    "total_calls": e.total_calls,
                    "total_success": e.total_success,
                    "cooldown_until": e.cooldown_until,
                    "last_latency_ms": e.last_latency_ms,
                }
            with open(self._state_path(), "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _load_persisted_state(self) -> None:
        try:
            import json
            path = self._state_path()
            if not os.path.exists(path):
                return
            with open(path, "r") as f:
                data = json.load(f)
            for name, stats in data.items():
                if name in self._entries:
                    e = self._entries[name]
                else:
                    e = ModelEntry(name=name)
                    self._entries[name] = e
                e.failure_count = stats.get("failure_count", 0)
                e.total_calls = stats.get("total_calls", 0)
                e.total_success = stats.get("total_success", 0)
                e.cooldown_until = stats.get("cooldown_until", 0)
                e.last_latency_ms = stats.get("last_latency_ms", 0)
        except Exception:
            pass


# Global singleton
_model_router: Optional[ModelRouter] = None


def get_model_router(config: Optional[RouterConfig] = None) -> ModelRouter:
    global _model_router
    if _model_router is None:
        _model_router = ModelRouter(config=config)
    return _model_router
