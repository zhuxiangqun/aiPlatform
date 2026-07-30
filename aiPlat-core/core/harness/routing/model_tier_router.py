"""ModelTierRouter — T1-T5 tiered model selection based on task complexity.

Phase 12.2: reads llm_profile.yaml tiers config, maps ComplexityRouter output
to tier, returns cheapest available model in that tier.

Design:
  - complexity (0-5 continuous) → tier (T1-T5) → first available model
  - tier model list: [default_model] + fallback_models (tried in order)
  - health check: 30s cached is_model_healthy() to avoid per-request infra calls
  - degradation: all models in tier unavailable → log warning → fall back to T1
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from core.harness.meta.control_profile import ControlProfile

logger = logging.getLogger("aiplat.model_tier_router")


@dataclass
class TierConfig:
    label: str
    complexity_range: Tuple[float, float]
    default_model: str
    fallback_models: List[str] = field(default_factory=list)
    max_tools: int = 0  # Phase 16: tool limit per tier


class ModelTierRouter:
    """T1-T5 tiered model router. Complexity → tier → cheapest capable model."""

    def __init__(self, config_path: str = None):
        self._tiers: Dict[str, TierConfig] = {}
        self._health_cache: Dict[str, Tuple[bool, float]] = {}
        self._health_cache_ttl = 30  # seconds
        self._load_tiers(config_path)

    def _load_tiers(self, config_path: str = None):
        """Load tiers from llm_profile.yaml or env-provided path."""
        try:
            import yaml
            from pathlib import Path

            if not config_path:
                config_path = os.getenv(
                    "AIPLAT_LLM_CONFIG_PATH",
                    str(Path(__file__).resolve().parent.parent.parent.parent.parent /
                        "aiPlat-infra" / "config" / "infra" / "llm_profile.yaml"),
                )
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
            tiers_raw = data.get("tiers", {})
            for tier_id, cfg in tiers_raw.items():
                if not isinstance(cfg, dict):
                    continue
                rng = cfg.get("complexity_range", [0, 5])
                self._tiers[tier_id] = TierConfig(
                    label=cfg.get("label", tier_id),
                    complexity_range=(float(rng[0]), float(rng[1])),
                    default_model=cfg.get("default_model", ""),
                    fallback_models=cfg.get("fallback_models", []),
                    max_tools=int(cfg.get("max_tools", 0)),
                )
            if not self._tiers:
                logger.warning("No tiers configured in llm_profile.yaml — router will return None")
        except Exception as e:
            logger.warning("Failed to load tiers: %s", e)

    # ── Complexity normalization ──────────────────────────────

    def _normalize_complexity(self, level: str, confidence: float) -> float:
        """Map ComplexityRouter output → 0-5 continuous score.

        simple  → center 0.5, range [0, 1]
        medium  → center 2.5, range [2, 3]
        complex → center 4.5, range [4, 5]

        Confidence as offset: high confidence → closer to center;
        low confidence → closer to boundary (conservative → higher tier).
        """
        base = {"simple": 0.5, "medium": 2.5, "complex": 4.5}
        centre = base.get(level, 2.5)
        offset = (1.0 - confidence) * 0.5

        # Deterministic tie-breaking: hash model name % 2 to decide direction
        direction = 1 if hash(level) % 2 == 0 else -1

        return max(0.0, min(5.0, centre + offset * direction))

    def _complexity_to_tier(self, score: float) -> int:
        """Map 0-5 score → tier number (1-5).

        Uses left-closed-right-open [low, high) so boundary values
        naturally fall into the next higher tier (conservative).
        """
        for tier_id, config in sorted(self._tiers.items()):
            low, high = config.complexity_range
            if low <= score < high:
                return int(tier_id.replace("T", ""))
        return 2  # default T2

    # ── Health check ──────────────────────────────────────────

    def _is_model_available(self, model_name: str) -> bool:
        """Cached health check (30s TTL). 使用 ModelManager 验证模型存在且已启用。"""
        now = time.time()
        cached = self._health_cache.get(model_name)
        if cached and now - cached[1] < self._health_cache_ttl:
            return cached[0]

        healthy = False
        try:
            from infra.management.model.manager import ModelManager
            mgr = ModelManager()
            model = mgr._find_model_by_name(model_name)
            healthy = model is not None and model.enabled
        except Exception:
            healthy = False  # 无法检查 → 保守不可用

        self._health_cache[model_name] = (healthy, now)
        return healthy

    # ── Core routing ──────────────────────────────────────────

    def route(self, purpose: str, level: str, confidence: float = 0.8) -> Optional[str]:
        """Core routing: complexity → tier → cheapest capable model.

        Args:
            purpose: Task purpose (e.g. "chat", "code_gen").
            level: ComplexityRouter level ("simple" | "medium" | "complex").
            confidence: ComplexityRouter confidence score (0-1).

        Returns model name string, or None if no tier is configured.
        """
        if not self._tiers:
            return None

        score = self._normalize_complexity(level, confidence)
        tier_num = self._complexity_to_tier(score)
        tier_id = f"T{tier_num}"
        config = self._tiers.get(tier_id)

        if not config:
            logger.debug("Tier %s not configured, falling back to T2", tier_id)
            t2 = self._tiers.get("T2")
            return t2.default_model if t2 else None

        # Try tier models in order: default → fallbacks
        tier_models = [config.default_model] + config.fallback_models
        for model_name in tier_models:
            if not model_name:
                continue
            if self._is_model_available(model_name):
                logger.debug(
                    "Routed to %s (tier=%s, level=%s, confidence=%.2f, score=%.1f)",
                    model_name, tier_id, level, confidence, score,
                )
                return model_name

        # All unavailable → degrade to T1
        logger.warning(
            "Tier %s all models unavailable (purpose=%s, level=%s), falling back to T1",
            tier_id, purpose, level,
        )
        t1_config = self._tiers.get("T1")
        return t1_config.default_model if t1_config else None

    def route_with_profile(
        self,
        purpose: str,
        level: str,
        confidence: float = 0.8,
        profile: Optional["ControlProfile"] = None,
    ) -> Optional[str]:
        if profile is not None and profile.model_tier not in ("auto", "", "by_complexity"):
            tier_id = profile.model_tier
            config = self._tiers.get(tier_id)
            if config:
                tier_models = [config.default_model] + config.fallback_models
                for model_name in tier_models:
                    if model_name and self._is_model_available(model_name):
                        logger.debug(
                            "Routed by profile override: %s (tier=%s, purpose=%s)",
                            model_name, tier_id, purpose,
                        )
                        return model_name
        return self.route(purpose, level, confidence)

    def get_max_tools(self, tier_id: str) -> int:
        """Return max tools limit for a tier. Default 0 (unlimited)."""
        config = self._tiers.get(tier_id)
        if config:
            return getattr(config, 'max_tools', 0) or 0
        return 0


# ── Singleton ────────────────────────────────────────────────

_router: Optional[ModelTierRouter] = None


def get_tier_router() -> ModelTierRouter:
    global _router
    if _router is None:
        _router = ModelTierRouter()
    return _router
