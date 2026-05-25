"""
Model Router — task-aware dynamic model selection with failure fallback.

**DEPRECATED** as of 2026-05. Model selection, failover, and health tracking
have been migrated to aiPlat-infra's ModelManager. This module is retained
for backward compatibility only and will be removed in a future release.

Use infra's ModelManager.list_models() and LLMClient for model access.

--- (legacy code below, do not extend) ---

Replaces the hardcoded single-model pattern in sys_llm_generate with a
deployment-aware router that:
  1. Picks the best model for the current task
  2. Falls back to alternatives on failure
  3. Tracks per-deployment health (cooldown on repeated failures)

Per infra §5.2: router lives in core (harness layer), queries ModelRegistry
from infra for model metadata.
"""

from __future__ import annotations

import os
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .model_registry import ModelEntry, ModelRegistry, get_model_registry


def _resolve_registry():
    """Try infra ModelManager first, fall back to legacy ModelRegistry."""
    try:
        from infra.management.model.manager import ModelManager
        mgr = ModelManager()
        # Wrap infra ModelManager as legacy-compatible registry
        registry_proxy = ModelRegistry()
        for m in mgr._models.values():
            registry_proxy.register(ModelEntry(
                name=m.name, provider=m.provider,
                api_key_env=m.config.api_key_env or "",
                base_url=m.config.base_url or "",
                enabled=m.enabled,
                capabilities=m.capabilities or ["chat"],
            ))
        return registry_proxy
    except Exception:
        return get_model_registry()


# ── Router configuration ──────────────────────────────────────────────

@dataclass
class RouterConfig:
    """Configuration for the model router."""
    max_consecutive_failures: int = 3     # failures before cooldown
    cooldown_duration_seconds: float = 30.0
    health_check_interval_seconds: float = 60.0
    prefer_cheapest: bool = False         # when True, prefer cheapest over primary
    try_cheaper_on_rate_limit: bool = True


# ── Router ────────────────────────────────────────────────────────────

class ModelRouter:
    """Task-aware model selector with failure fallback and persistence."""

    def __init__(
        self,
        config: Optional[RouterConfig] = None,
        registry: Optional[ModelRegistry] = None,
    ):
        self._config = config or RouterConfig()
        self._registry = registry or _resolve_registry()
        self._fallback_history: Dict[str, List[str]] = {}
        self._load_persisted_state()  # model_name → tried deployments

    async def select(
        self,
        model_name: str = "",
        task_purpose: str = "",          # "agent" / "document" / "default"
        task_complexity: str = "medium",  # low/medium/high
        task_budget: Optional[float] = None,
    ) -> Optional[ModelEntry]:
        """Select the best model deployment for a task.

        Resolution order:
        1. If model_name is given → use directly
        2. If task_purpose is given → resolve via registry.get_default_for_purpose()
        3. Default to "deepseek-chat"

        Then: get healthy candidates, prefer cheaper for low-complexity tasks.
        Returns None if no healthy deployment available.
        """
        if not model_name and task_purpose:
            model_name = self._registry.get_default_for_purpose(task_purpose)
        if not model_name:
            model_name = self._registry.get_default_for_purpose("default")

        candidates = self._registry.get_candidates(model_name)

        # Prefer higher success rate; shuffle in future
        candidates.sort(key=lambda e: e.success_rate, reverse=True)

        # Try cheaper alternative for low-complexity tasks
        if task_complexity == "low" and self._config.prefer_cheapest:
            alt = self._registry.get_cheaper_alternative(model_name)
            if alt:
                candidates = [alt] + candidates

        # Try cheaper alternative for low-complexity tasks
        if task_complexity == "low" and self._config.prefer_cheapest:
            alt = self._registry.get_cheaper_alternative(model_name)
            if alt:
                candidates = [alt] + candidates

        # Exclude already-failed deployments for this call
        tried = set(self._fallback_history.get(model_name, []))
        candidates = [c for c in candidates if c.name not in tried]

        if not candidates:
            # Fallback to infra layer's model registry (Phase A wiring)
            from .infra_bridge import list_infra_models, get_infra_model_source
            infra_models = list_infra_models()
            if infra_models:
                for im in infra_models:
                    im_name = im.get("name") if isinstance(im, dict) else getattr(im, "name", None)
                    im_provider = im.get("provider") if isinstance(im, dict) else getattr(im, "provider", "deepseek")
                    im_api_key = im.get("api_key_env") if isinstance(im, dict) else getattr(im, "api_key_env", "DEEPSEEK_API_KEY")
                    im_desc = im.get("description") if isinstance(im, dict) else getattr(im, "description", "")
                    if im_name == model_name or task_purpose:
                        candidates.append(ModelEntry(
                            name=im_name or model_name,
                            provider=im_provider or "deepseek",
                            api_key_env=im_api_key or "DEEPSEEK_API_KEY",
                        ))
                if candidates:
                    return candidates[0]
            return None

        return candidates[0]

    def clear_fallback_history(self, model_name: str) -> None:
        self._fallback_history.pop(model_name, None)

    # ── Persistence (survives process restart) ──

    def _state_path(self) -> str:
        import os
        from pathlib import Path
        home = os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat"))
        return str(Path(home) / "model_router_state.json")

    def _persist_state(self) -> None:
        try:
            import json
            data = {}
            for name, entries in self._registry._models.items():
                data[name] = {
                    "failure_count": entries[0].failure_count if entries else 0,
                    "total_calls": entries[0].total_calls if entries else 0,
                    "total_success": entries[0].total_success if entries else 0,
                    "cooldown_until": entries[0].cooldown_until if entries else 0,
                    "last_latency_ms": entries[0].last_latency_ms if entries else 0,
                }
            path = self._state_path()
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _load_persisted_state(self) -> None:
        try:
            import json
            path = self._state_path()
            if not __import__("os").path.exists(path):
                return
            with open(path, "r") as f:
                data = json.load(f)
            for name, stats in data.items():
                entries = self._registry._models.get(name, [])
                for e in entries:
                    e.failure_count = stats.get("failure_count", 0)
                    e.total_calls = stats.get("total_calls", 0)
                    e.total_success = stats.get("total_success", 0)
                    e.cooldown_until = stats.get("cooldown_until", 0)
                    e.last_latency_ms = stats.get("last_latency_ms", 0)
        except Exception:
            pass

    def mark_success(self, model_name: str, entry: ModelEntry) -> None:
        """Reset failure counter on success and track call metrics."""
        entry.total_calls += 1
        entry.total_success += 1
        entry.failure_count = 0
        if model_name in self._fallback_history:
            del self._fallback_history[model_name]
        self._persist_state()

    def mark_failure(self, model_name: str, entry: ModelEntry) -> None:
        """Record a failure, apply cooldown if threshold exceeded."""
        entry.total_calls += 1
        entry.failure_count += 1
        if entry.failure_count >= self._config.max_consecutive_failures:
            entry.cooldown_until = time.time() + self._config.cooldown_duration_seconds
            entry.failure_count = 0

        # Record what we tried so the retry can skip it
        if model_name not in self._fallback_history:
            self._fallback_history[model_name] = []
        self._fallback_history[model_name].append(entry.name)
        self._persist_state()

    def clear_fallback_history(self, model_name: str) -> None:
        self._fallback_history.pop(model_name, None)


# Global singleton
_model_router: Optional[ModelRouter] = None


def get_model_router(config: Optional[RouterConfig] = None) -> ModelRouter:
    global _model_router
    if _model_router is None:
        _model_router = ModelRouter(config=config)
    return _model_router
