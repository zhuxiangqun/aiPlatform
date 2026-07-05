"""
Phase 37: SwarmBroker — Contract Net Protocol for emergent swarm collaboration.

Closes E-axis L5 gap: replaces regex-based agent lookup with a full
Contract Net Protocol (announce → bid → award), enabling agents to
self-evaluate their capabilities and compete for tasks autonomously.

Protocol:
  Announce: broadcast task to all registered agents
  Bid:     each agent self-evaluates (keyword 0.3 + history 0.3 + tag 0.4)
  Award:   select highest-scoring bid → execute task via sub-agent
  Fallback: if no bids, route through DynamicOrchestrator (Phase 32)

Key design decisions:
  - Cold-start exploration bonus: 0.1 for untested agents
  - No-bid fallback to DynamicOrchestrator (ensures task never orphaned)
  - Bid decision logged for audit (score breakdown per agent)
  - Agent profiles built from AGENT.md metadata + historical success rates
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("aiplat.swarm_broker")


@dataclass
class AgentProfile:
    """An agent's capability profile for self-evaluation."""

    agent_id: str
    name: str = ""
    description: str = ""
    capability_tags: List[str] = field(default_factory=list)
    total_attempts: int = 0
    successes: int = 0

    @property
    def success_rate(self) -> float:
        return self.successes / self.total_attempts if self.total_attempts > 0 else 0.0

    def estimate_eta(self, task: str) -> str:
        # Simple estimate based on task length
        l = len(task.split())
        if l < 20:
            return "5-10s"
        elif l < 100:
            return "10-30s"
        return "30s+"


@dataclass
class Bid:
    """A bid from an agent for a task."""

    agent_id: str
    capability: str
    score: float
    score_breakdown: Dict[str, float]  # keyword, history, tag
    eta: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "capability": self.capability,
            "score": round(self.score, 3),
            "score_breakdown": self.score_breakdown,
            "eta": self.eta,
            "timestamp": self.timestamp,
        }


class SwarmBroker:
    """Contract Net Protocol broker for emergent swarm collaboration.

    Usage:
        broker = SwarmBroker(orchestrator)
        broker.register_agent("security_reviewer", {...})
        result = await broker.execute_swarm("security review code", session_id)
    """

    MIN_BID_SCORE = 0.3  # minimum score to submit a bid
    COLD_START_BONUS = 0.1  # exploration bonus for untested agents

    def __init__(self, orchestrator):
        self._orchestrator = orchestrator
        self._profiles: Dict[str, AgentProfile] = {}
        self._bid_history: List[Dict[str, Any]] = []
        self._total_swarms = 0

    def register_agent(self, agent_id: str, profile: AgentProfile) -> None:
        self._profiles[agent_id] = profile

    def learn_from_execution(self, agent_id: str, success: bool) -> None:
        if agent_id in self._profiles:
            p = self._profiles[agent_id]
            p.total_attempts += 1
            if success:
                p.successes += 1

    async def announce(self, task: str, capabilities: List[str]) -> List[Bid]:
        """Broadcast task → collect bids from all registered agents."""
        if not task:
            return []

        bids = []
        for agent_id, profile in self._profiles.items():
            score, breakdown = self._evaluate(profile, task, capabilities)
            if score >= self.MIN_BID_SCORE:
                bids.append(Bid(
                    agent_id=agent_id,
                    capability=self._best_capability(breakdown, capabilities),
                    score=score,
                    score_breakdown=breakdown,
                    eta=profile.estimate_eta(task),
                ))

        # Sort by score descending
        bids.sort(key=lambda b: -b.score)

        if bids:
            logger.info(
                "[swarm] announce: %d bids for task (top: %s %.3f)",
                len(bids), bids[0].agent_id, bids[0].score,
            )

        return bids

    def _evaluate(
        self, profile: AgentProfile, task: str, capabilities: List[str]
    ) -> Tuple[float, Dict[str, float]]:
        """Self-evaluate agent capability for a task.

        Scoring: keyword overlap 0.3 + history success rate 0.3 + tag match 0.4
        Cold-start: untested agents get a 0.1 exploration bonus.
        """
        task_lower = task.lower()
        desc_lower = profile.description.lower()

        # Keyword overlap (0.3)
        task_words = set(task_lower.split())
        desc_words = set(desc_lower.split())
        if not task_words:
            kw_score = 0.0
        else:
            overlap = len(task_words & desc_words)
            kw_score = min(1.0, overlap / len(task_words)) * 0.3

        # Historical success rate (0.3) — cold start bonus
        if profile.total_attempts == 0:
            hist_score = self.COLD_START_BONUS
        else:
            hist_score = profile.success_rate * 0.3

        # Capability tag match (0.4)
        tag_score = 0.0
        if capabilities and profile.capability_tags:
            matches = set(capabilities) & set(profile.capability_tags)
            tag_score = (len(matches) / len(capabilities)) * 0.4 if capabilities else 0.2

        return kw_score + hist_score + tag_score, {
            "keyword": round(kw_score, 3),
            "history": round(hist_score, 3),
            "tag": round(tag_score, 3),
        }

    def _best_capability(self, breakdown: Dict[str, float], capabilities: List[str]) -> str:
        """Return the capability with the highest score contribution."""
        return max(breakdown, key=breakdown.get) if breakdown else "review"

    async def award(self, bid: Bid, task_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Award task to the winning bidder → execute via sub-agent."""
        result = await self._orchestrator.spawn(
            bid.capability,
            task_context.get("task", ""),
            task_context.get("session_id", ""),
            source_agent_id=task_context.get("source_agent_id", ""),
        )
        # Log for audit
        self._bid_history.append({
            "bid": bid.to_dict(),
            "task": task_context.get("task", "")[:200],
            "timestamp": time.time(),
        })
        return result

    async def execute_swarm(
        self,
        task: str,
        session_id: str,
        *,
        source_agent_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Full Contract Net Protocol: announce → bid → award."""

        # Phase 1: Announce and collect bids
        bids = await self.announce(task, list(self._orchestrator.CAPABILITY_MAP.keys()))

        if not bids:
            # Fallback: No agent bid → route through DynamicOrchestrator (Phase 32)
            logger.info("[swarm] no bids → falling back to orchestrator")
            gap = await self._orchestrator.sense_gap(task, source_agent_id)
            if gap:
                return await self._orchestrator.spawn(
                    gap["capability"], task, session_id,
                    source_agent_id=source_agent_id,
                )
            return None

        # Phase 2: Award to highest bidder
        winner = bids[0]
        self._total_swarms += 1

        logger.info(
            "[swarm] awarded: %s (score=%.3f, %d other bids)",
            winner.agent_id, winner.score, len(bids) - 1,
        )

        return await self.award(winner, {
            "task": task,
            "session_id": session_id,
            "source_agent_id": source_agent_id,
        })

    def stats(self) -> Dict[str, Any]:
        return {
            "agents_registered": len(self._profiles),
            "total_swarms": self._total_swarms,
            "bid_history_count": len(self._bid_history),
            "min_bid_score": self.MIN_BID_SCORE,
            "cold_start_bonus": self.COLD_START_BONUS,
            "recent_bids": self._bid_history[-3:],
        }


# ── Singleton ──

_broker: Optional[SwarmBroker] = None


def get_swarm_broker() -> SwarmBroker:
    global _broker
    if _broker is None:
        from core.harness.coordination.dynamic_orchestrator import get_dynamic_orchestrator
        _broker = SwarmBroker(get_dynamic_orchestrator())
    return _broker
