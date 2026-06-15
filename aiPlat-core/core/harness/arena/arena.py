"""
Darwin Arena — Multi-agent competition benchmark with champion promotion.

Inspired by ROSClaw's rosclaw-darwin: pits agent variants against each other
on benchmark tasks, ranks by Elo, and auto-promotes champions.

Completely manual trigger — no background/auto-scheduling to control LLM costs.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

log = logging.getLogger(__name__)


# ============================================================
# Scoring
# ============================================================

class EloScorer:
    """
    Bayesian Elo rating system.
    
    K-factor adaptive: higher K for new/unstable ratings, lower for mature ratings.
    """

    def __init__(self, initial_rating: float = 1500.0, k_base: float = 32.0):
        self._ratings: Dict[str, float] = {}
        self._matches: Dict[str, int] = {}  # contender → match count
        self._initial = initial_rating
        self._k_base = k_base

    def get_rating(self, name: str) -> float:
        return self._ratings.get(name, self._initial)

    def record_match(self, winner: str, loser: str, *, draw: bool = False) -> tuple:
        wa = self._ratings.setdefault(winner, self._initial)
        wb = self._ratings.setdefault(loser, self._initial)

        ea = 1.0 / (1.0 + 10.0 ** ((wb - wa) / 400.0))
        eb = 1.0 - ea

        # Adaptive K-factor
        kw = self._k_factor(winner)
        kl = self._k_factor(loser)

        if draw:
            sa, sb = 0.5, 0.5
        else:
            sa, sb = 1.0, 0.0

        new_wa = wa + kw * (sa - ea)
        new_wb = wb + kl * (sb - eb)

        self._ratings[winner] = new_wa
        self._ratings[loser] = new_wb
        self._matches[winner] = self._matches.get(winner, 0) + 1
        self._matches[loser] = self._matches.get(loser, 0) + 1

        return (new_wa, new_wb)

    def leaderboard(self) -> List[Dict[str, Any]]:
        ranked = sorted(self._ratings.items(), key=lambda x: x[1], reverse=True)
        return [
            {"name": name, "rating": round(rating, 1), "matches": self._matches.get(name, 0)}
            for name, rating in ranked
        ]

    def _k_factor(self, name: str) -> float:
        matches = self._matches.get(name, 0)
        if matches < 10:
            return self._k_base * 1.5   # new contender, high uncertainty
        elif matches < 30:
            return self._k_base
        else:
            return self._k_base * 0.5   # well-established


# ============================================================
# Champion promotion
# ============================================================

@dataclass
class ChampionResult:
    name: str
    rating: float
    win_rate: float
    promoted: bool = False
    promotion_reason: str = ""


class ChampionPipeline:
    """
    Evaluates contender vs gate criteria and promotes to champion.
    
    Criteria:
      1. Rating ≥ threshold (default: 1550)
      2. Win rate ≥ threshold (default: 60%)
      3. Minimum matches played (default: 5)
    """

    def __init__(
        self,
        *,
        rating_threshold: float = 1550.0,
        win_rate_threshold: float = 0.60,
        min_matches: int = 5,
    ):
        self.rating_threshold = rating_threshold
        self.win_rate_threshold = win_rate_threshold
        self.min_matches = min_matches
        self._champions: Set[str] = set()

    def evaluate(
        self, name: str, scorer: EloScorer, match_results: List[Dict[str, Any]]
    ) -> ChampionResult:
        """
        Evaluate whether a contender should be promoted to champion.
        """
        rating = scorer.get_rating(name)
        matches = scorer._matches.get(name, 0)

        wins = sum(1 for m in match_results if m.get("winner") == name)
        win_rate = wins / max(matches, 1)

        if name in self._champions:
            return ChampionResult(name=name, rating=rating, win_rate=win_rate,
                                  promoted=False, promotion_reason="already champion")

        if matches < self.min_matches:
            return ChampionResult(name=name, rating=rating, win_rate=win_rate,
                                  promoted=False, promotion_reason=f"insufficient matches ({matches}/{self.min_matches})")

        if rating < self.rating_threshold:
            return ChampionResult(name=name, rating=rating, win_rate=win_rate,
                                  promoted=False, promotion_reason=f"rating too low ({rating:.0f}/{self.rating_threshold})")

        if win_rate < self.win_rate_threshold:
            return ChampionResult(name=name, rating=rating, win_rate=win_rate,
                                  promoted=False, promotion_reason=f"win rate too low ({win_rate:.1%}/{self.win_rate_threshold:.0%})")

        self._champions.add(name)
        return ChampionResult(name=name, rating=rating, win_rate=win_rate,
                              promoted=True, promotion_reason="all criteria met")

    @property
    def champions(self) -> Set[str]:
        return self._champions

    def is_champion(self, name: str) -> bool:
        return name in self._champions


# ============================================================
# Arena
# ============================================================

@dataclass
class ArenaMatch:
    contender_a: str
    contender_b: str
    winner: Optional[str] = None
    score_a: float = 0.0
    score_b: float = 0.0
    duration_s: float = 0.0
    error: Optional[str] = None


@dataclass
class ArenaResult:
    matches: List[ArenaMatch] = field(default_factory=list)
    leaderboard: List[Dict[str, Any]] = field(default_factory=list)
    promotions: List[ChampionResult] = field(default_factory=list)
    total_duration_s: float = 0.0


class DarwinArena:
    """
    Multi-agent competition arena.
    
    Manual trigger only. Configure contenders, run round-robin or head-to-head,
    and promote champions.
    
    Usage:
      arena = DarwinArena()
      result = await arena.round_robin(
          contenders=[("agent-a", fn_a), ("agent-b", fn_b)],
          benchmark_fn=lambda name, fn: run_benchmark(name, fn),
      )
    """

    def __init__(self):
        self._scorer = EloScorer()
        self._pipeline = ChampionPipeline()
        self._history: List[ArenaMatch] = []

    @property
    def scorer(self) -> EloScorer:
        return self._scorer

    @property
    def pipeline(self) -> ChampionPipeline:
        return self._pipeline

    async def round_robin(
        self,
        *,
        contenders: List[tuple],  # (name, agent_fn)
        benchmark_fn,             # async (name, agent_fn) → float (score)
        matches_per_pair: int = 3,
        on_match: callable = None,  # async callback per match
    ) -> ArenaResult:
        """
        Run round-robin tournament among contenders.
        
        Args:
            contenders: List of (name, agent_function) pairs
            benchmark_fn: Async function that runs a benchmark and returns a score
            matches_per_pair: How many matches per head-to-head pair
            on_match: Optional async callback(match) after each match
        """
        result = ArenaResult()
        start = time.time()

        for i in range(len(contenders)):
            for j in range(i + 1, len(contenders)):
                name_a, fn_a = contenders[i]
                name_b, fn_b = contenders[j]

                for round_num in range(matches_per_pair):
                    match = ArenaMatch(contender_a=name_a, contender_b=name_b)
                    m_start = time.time()
                    try:
                        score_a = await benchmark_fn(name_a, fn_a)
                        score_b = await benchmark_fn(name_b, fn_b)
                        match.score_a = score_a
                        match.score_b = score_b
                        match.winner = name_a if score_a > score_b else (name_b if score_b > score_a else None)
                        if match.winner:
                            loser = name_b if match.winner == name_a else name_a
                            self._scorer.record_match(match.winner, loser)
                    except Exception as e:
                        match.error = str(e)
                    match.duration_s = time.time() - m_start
                    result.matches.append(match)
                    self._history.append(match)

                    if on_match:
                        await on_match(match)

        # Leaderboard
        result.leaderboard = self._scorer.leaderboard()

        # Champion evaluation
        for name, _ in contenders:
            champ = self._pipeline.evaluate(name, self._scorer, [
                {"winner": m.winner} for m in self._history
                if m.contender_a == name or m.contender_b == name
            ])
            if champ.promoted:
                result.promotions.append(champ)

        result.total_duration_s = time.time() - start
        log.info(
            "Arena round-robin complete: %d matches, %d contenders, %.1fs",
            len(result.matches), len(contenders), result.total_duration_s,
        )
        return result

    def leaderboard(self) -> List[Dict[str, Any]]:
        return self._scorer.leaderboard()

    def history(self, limit: int = 50) -> List[ArenaMatch]:
        return self._history[-limit:]

    def to_persist_state(self) -> Dict[str, Any]:
        """Serialize arena state for persistence."""
        return {
            "leaderboard": self._scorer.leaderboard(),
            "matches": [
                {"a": m.contender_a, "b": m.contender_b, "winner": m.winner,
                 "score_a": m.score_a, "score_b": m.score_b, "duration_s": m.duration_s}
                for m in self._history
            ],
            "total_matches": len(self._history),
            "promotions": [
                {"name": p.name, "rating": p.rating, "promoted": p.promoted}
                for p in (self._pipeline._champions or set()) if True
            ] if hasattr(self._pipeline, '_champions') else [],
        }

    def from_persist_state(self, state: Dict[str, Any]) -> None:
        """Restore arena state from persisted data."""
        if not state:
            return
        for entry in state.get("leaderboard", []):
            self._scorer._ratings[entry["name"]] = entry["rating"]
            self._scorer._matches[entry["name"]] = entry.get("matches", 0)
        for m in state.get("matches", []):
            self._history.append(ArenaMatch(
                contender_a=m.get("a", ""), contender_b=m.get("b", ""),
                winner=m.get("winner"), score_a=m.get("score_a", 0),
                score_b=m.get("score_b", 0), duration_s=m.get("duration_s", 0),
            ))


__all__ = [
    "DarwinArena", "EloScorer", "ChampionPipeline",
    "ArenaMatch", "ArenaResult", "ChampionResult",
]
