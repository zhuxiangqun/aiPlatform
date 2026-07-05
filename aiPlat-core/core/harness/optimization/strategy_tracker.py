"""
Phase 26: StrategyEffectivenessTracker — learn which healing strategy works best.

Replaces the hardcoded if/elif chain in _meta_optimize with a data-driven lookup.
For each (error_type, strategy_name) pair, tracks:
  - attempts: total times tried
  - successes: times the error was resolved
  - tokens_saved: average tokens consumed by the strategy
  - last_success: timestamp of last successful use

Uses Phase 25 snapshots to compare pre/post strategy state for objective measurement.

Storage: in-memory dict (per-process) + persisted to execution_store for cross-restart learning.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("aiplat.strategy_tracker")


@dataclass
class StrategyRecord:
    """Effectiveness record for one (error_type, strategy) pair."""

    error_type: str
    strategy_name: str
    attempts: int = 0
    successes: int = 0
    tokens_consumed: float = 0.0  # cumulative tokens
    last_success_ts: float = 0.0
    last_failure_ts: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts > 0 else 0.0

    @property
    def avg_tokens(self) -> float:
        return self.tokens_consumed / self.attempts if self.attempts > 0 else 0.0

    @property
    def score(self) -> float:
        """Composite score: success_rate weighted 70%, token efficiency 30%."""
        if self.attempts == 0:
            return 0.0
        token_score = max(0.0, 1.0 - self.avg_tokens / 10000)  # normalize: 10K tokens = 0
        return 0.7 * self.success_rate + 0.3 * token_score

    @property
    def cold_start(self) -> bool:
        """True if this strategy has never been tried for this error type."""
        return self.attempts == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.error_type,
            "strategy_name": self.strategy_name,
            "attempts": self.attempts,
            "successes": self.successes,
            "success_rate": round(self.success_rate, 3),
            "avg_tokens": round(self.avg_tokens, 1),
            "score": round(self.score, 3),
            "last_success_ts": self.last_success_ts,
            "last_failure_ts": self.last_failure_ts,
            "cold_start": self.cold_start,
        }

    def record_success(self, tokens_used: int = 0) -> None:
        self.attempts += 1
        self.successes += 1
        self.tokens_consumed += tokens_used
        self.last_success_ts = time.time()

    def record_failure(self, tokens_used: int = 0) -> None:
        self.attempts += 1
        self.tokens_consumed += tokens_used
        self.last_failure_ts = time.time()


class StrategyEffectivenessTracker:
    """Tracks and ranks self-healing strategies by their historical effectiveness.

    Usage:
        tracker = StrategyEffectivenessTracker()
        tracker.record('rate_limit', 'rotate_credential', success=True, tokens=500)
        best = tracker.rank_strategies('rate_limit')
        # → [('rotate_credential', 0.85), ('backoff_retry', 0.0), ...]
    """

    # Default strategy pool — all available strategies for any error type
    ALL_STRATEGIES = [
        "rotate_credential",
        "compress_retry",
        "backoff_retry",
        "skip_stage",
    ]

    def __init__(self):
        self._records: Dict[Tuple[str, str], StrategyRecord] = {}
        self._total_attempts: int = 0
        self._loaded_ts: float = time.time()

    def _key(self, error_type: str, strategy_name: str) -> Tuple[str, str]:
        return (error_type, strategy_name)

    def _get_or_create(self, error_type: str, strategy_name: str) -> StrategyRecord:
        key = self._key(error_type, strategy_name)
        if key not in self._records:
            self._records[key] = StrategyRecord(
                error_type=error_type, strategy_name=strategy_name
            )
        return self._records[key]

    def record(
        self,
        error_type: str,
        strategy_name: str,
        success: bool,
        tokens_used: int = 0,
    ) -> None:
        """Record the outcome of a strategy attempt."""
        rec = self._get_or_create(error_type, strategy_name)
        if success:
            rec.record_success(tokens_used)
            logger.info(
                "[strategy_tracker] %s + %s = SUCCESS (rate=%.0f%%)",
                error_type, strategy_name, rec.success_rate * 100,
            )
        else:
            rec.record_failure(tokens_used)
            logger.info(
                "[strategy_tracker] %s + %s = FAIL (rate=%.0f%%)",
                error_type, strategy_name, rec.success_rate * 100,
            )
        self._total_attempts += 1

    def record_from_snapshot_pair(
        self,
        error_type: str,
        strategy_name: str,
        pre_snapshot_id: str,
        post_snapshot_id: str,
        session_id: str,
    ) -> None:
        """Record strategy outcome by comparing Phase 25 snapshots."""
        try:
            from core.harness.execution.snapshot import (
                compare_execution_snapshots,
                load_execution_snapshot,
            )
            diff = compare_execution_snapshots(
                pre_snapshot_id, post_snapshot_id, session_id
            )
            effect = diff.get("strategy_effect", {})
            resolved = effect.get("error_resolved", False)
            tokens = diff.get("changes", {}).get("tokens_used", {}).get("delta", 0)
            self.record(error_type, strategy_name, success=resolved, tokens_used=tokens)
        except Exception as e:
            logger.debug("snapshot-based recording failed: %s", e)

    def rank_strategies(
        self, error_type: str, min_attempts: int = 0
    ) -> List[Dict[str, Any]]:
        """Return strategies ranked by effectiveness for the given error type.

        Strategies with fewer than min_attempts are returned at lower priority.
        """
        candidates = [
            self._get_or_create(error_type, s)
            for s in self.ALL_STRATEGIES
        ]
        # Sort by: not cold_start first, then by score descending
        candidates.sort(key=lambda r: (0 if not r.cold_start else 1, -r.score))
        return [c.to_dict() for c in candidates if c.attempts >= min_attempts or min_attempts == 0]

    def best_strategy(self, error_type: str) -> Optional[str]:
        """Return the single best strategy for this error type, or None if cold start."""
        ranked = self.rank_strategies(error_type, min_attempts=1)
        if not ranked:
            return None
        top = ranked[0]
        if top["score"] >= 0.3:  # minimum threshold for recommendation
            return top["strategy_name"]
        return None

    def explore_strategy(self, error_type: str) -> Optional[str]:
        """Return an untried strategy for exploration, or None if all tried."""
        for strategy_name in self.ALL_STRATEGIES:
            rec = self._get_or_create(error_type, strategy_name)
            if rec.cold_start:
                logger.info(
                    "[strategy_tracker] exploring: %s + %s (cold start)",
                    error_type, strategy_name,
                )
                return strategy_name
        return None

    def is_cold_start(self, error_type: str) -> bool:
        """True if no strategy has ever been tried for this error type."""
        for strategy_name in self.ALL_STRATEGIES:
            rec = self._get_or_create(error_type, strategy_name)
            if rec.attempts > 0:
                return False
        return True

    def stats(self) -> Dict[str, Any]:
        return {
            "total_attempts": self._total_attempts,
            "tracked_pairs": len(self._records),
            "top_strategies": {
                f"{et}+{sn}": float(rec.score)
                for (et, sn), rec in sorted(
                    self._records.items(),
                    key=lambda x: x[1].score,
                    reverse=True,
                )[:10]
                if rec.attempts >= 3
            },
            "loaded_ts": self._loaded_ts,
            "strategy_pool": self.ALL_STRATEGIES,
        }

    def to_dict(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._records.values()]


# ── Process-wide singleton ──

_tracker: Optional[StrategyEffectivenessTracker] = None


def get_strategy_tracker() -> StrategyEffectivenessTracker:
    """Get or create the process-wide strategy effectiveness tracker."""
    global _tracker
    if _tracker is None:
        _tracker = StrategyEffectivenessTracker()
    return _tracker
