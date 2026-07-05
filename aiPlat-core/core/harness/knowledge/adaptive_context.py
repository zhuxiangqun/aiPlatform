"""
Phase 38: AdaptiveContextRouter — self-learning context source selection.

Closes B-axis L5 gap: replaces YAML-hardcoded data source selection with
runtime adaptive routing based on (task_type, source) historical effectiveness.

L5 characteristics:
  - select_sources(): chooses best data sources per task type
  - adapt_compression(): adapts compression level to token pressure
  - learn_from_outcome(): closed-loop feedback for continuous improvement
  - Cold-start: all sources tried at 0.5 baseline, learning shifts weights

Integration: called by MemoryManager.build_context() to determine which
sources to query and at what compression level.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.adaptive_context")


class AdaptiveContextRouter:
    """Self-learning context source selector for L5 context awareness.

    Usage:
        router = AdaptiveContextRouter(tracker)
        config = router.select_sources("security review", "code_review")
        # → {"sources": ["graph_index", "fts5"], "compression": "balanced", "confidence": 0.82}

        # After execution:
        router.learn_from_outcome("security review", "code_review", ["graph_index", "fts5"], 0.8)
    """

    ALL_SOURCES = ["caller", "graph_index", "datasource", "fts5", "hyde"]
    COMPRESSION_LEVELS = ["minimal", "balanced", "aggressive"]

    def __init__(self, tracker=None):
        self._tracker = tracker  # Phase 26 StrategyEffectivenessTracker
        self._selection_history: List[Dict[str, Any]] = []
        self._total_selections = 0

    def _ensure_tracker(self):
        if self._tracker is not None:
            return
        try:
            from core.harness.optimization.strategy_tracker import get_strategy_tracker
            self._tracker = get_strategy_tracker()
        except Exception:
            pass

    def select_sources(self, query: str, task_type: str) -> Dict[str, Any]:
        """Select optimal data sources and compression level for a query.

        Returns:
            {
                "sources": ["caller", "graph_index", "fts5"],
                "compression_level": "balanced",
                "confidence": 0.82
            }
        """
        self._ensure_tracker()

        task_type = task_type or "unknown"
        scores = {}

        # 1. Score each source based on historical effectiveness
        for src in self.ALL_SOURCES:
            key = f"ctx:{task_type}:{src}"
            if self._tracker:
                rec = self._tracker._get_or_create(key, "select_source")
                if rec.attempts > 0:
                    scores[src] = rec.success_rate
                else:
                    scores[src] = 0.5  # cold-start: 50% baseline
            else:
                scores[src] = 0.5

        # 2. Select top-scoring sources
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        selected = [s for s, score in ranked[:3] if score > 0.3]
        if not selected:
            selected = [ranked[0][0]]  # at least one

        # 3. Adaptive compression based on token pressure
        token_pressure = self._estimate_token_pressure(query)
        if token_pressure < 0.4:
            compression = "minimal"
        elif token_pressure < 0.7:
            compression = "balanced"
        else:
            compression = "aggressive"

        # 4. Confidence: average score of selected sources
        conf = sum(scores[s] for s in selected) / len(selected) if selected else 0.5

        self._total_selections += 1

        if self._total_selections <= 3:
            logger.info(
                "[adaptive_context] select: task=%s sources=%s compression=%s confidence=%.2f",
                task_type, selected, compression, conf,
            )

        return {
            "sources": selected,
            "compression_level": compression,
            "confidence": round(conf, 3),
            "all_scores": {s: round(sc, 3) for s, sc in scores.items()},
        }

    def learn_from_outcome(
        self,
        query: str,
        task_type: str,
        sources_used: List[str],
        helpfulness: float,  # 0-1, how helpful was the context?
    ) -> None:
        """Record context selection outcome for continuous learning."""
        self._ensure_tracker()
        if not self._tracker:
            return

        task_type = task_type or "unknown"
        success = helpfulness > 0.5

        for src in sources_used:
            key = f"ctx:{task_type}:{src}"
            self._tracker.record(key, "select_source", success=success)

        self._selection_history.append({
            "task_type": task_type,
            "sources": sources_used,
            "helpfulness": helpfulness,
            # Keep last 20
        })
        if len(self._selection_history) > 20:
            self._selection_history = self._selection_history[-20:]

        if self._total_selections > 0 and self._total_selections % 10 == 0:
            logger.info(
                "[adaptive_context] learned: task=%s sources=%s helpfulness=%.2f",
                task_type, sources_used, helpfulness,
            )

    def _estimate_token_pressure(self, query: str) -> float:
        """Estimate token pressure (0-1) based on query complexity."""
        l = len(query.split())
        if l < 50:
            return min(1.0, l * 1.3 / 1000)  # ~65/1000 = 0.065
        return min(1.0, l * 1.3 / 4000)  # larger baseline

    def stats(self) -> Dict[str, Any]:
        self._ensure_tracker()
        top_pairs = {}
        if self._tracker:
            for (key, rec) in self._tracker._records.items():
                if key[0].startswith("ctx:") and key[1] == "select_source" and rec.attempts >= 3:
                    top_pairs[key[0]] = round(rec.success_rate, 3)

        return {
            "total_selections": self._total_selections,
            "history_count": len(self._selection_history),
            "sources_pool": self.ALL_SOURCES,
            "compression_levels": self.COMPRESSION_LEVELS,
            "top_source_scores": dict(sorted(top_pairs.items(), key=lambda x: -x[1])[:10]),
        }


# ── Singleton ──

_router: Optional[AdaptiveContextRouter] = None


def get_adaptive_context_router() -> AdaptiveContextRouter:
    global _router
    if _router is None:
        _router = AdaptiveContextRouter()
    return _router
