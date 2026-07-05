"""
Phase 32: DynamicOrchestrator — on-demand sub-agent formation engine.

Closes the E-axis L5 gap: instead of fixed Pipeline stage ordering,
the system dynamically detects when a new capability is needed and
spawns the right sub-agent to handle it.

Core insight: This is NOT a swarm/emergent system. It's a lightweight
capability-gap detector that observes the ReAct loop's output, matches
needed capabilities against available sub-agents, and routes relevant
context to the spawned agent.

Architecture:
  ReActLoop.observe() output  →  DynamicOrchestrator.sense_gap()
    ↓
  capability matched?  →  SubagentCoordinator.execute_single()
    ↓
  no match?  →  ToolBootstrap (Phase 31) to create new skill
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.dynamic_orchestrator")


@dataclass
class OrchestrationEvent:
    """Record of a dynamic orchestration action."""

    event_id: str
    request_type: str  # "spawn" | "match" | "suggest"
    source_agent: str
    target_agent: str
    capability: str
    status: str  # "spawned" | "matched" | "failed" | "suggested"
    duration_ms: int
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "request_type": self.request_type,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "capability": self.capability,
            "status": self.status,
            "duration_ms": self.duration_ms,
        }


class DynamicOrchestrator:
    """On-demand sub-agent formation engine.

    Scans agent outputs for capability requests (e.g., "需要安全审查",
    "need a review", "请帮我...") and dynamically assigns sub-agents.

    Usage:
        orch = DynamicOrchestrator()
        match = await orch.sense_gap(agent_output, main_agent_id)
        if match:
            result = await orch.spawn(
                match.capability, task_context, session_id
            )
    """

    # Patterns that indicate a capability gap (more specific first)
    CAPABILITY_PATTERNS = [
        # Security-specific patterns (before generic "review")
        (r"安全.*审查|安全.*检查|security.*review|安全.*审计", "security"),
        # Capability-specific
        (r"需要.*review|需要.*审查|需要.*审核|需要.*检查|needs?\s+review", "review"),
        (r"需要.*refactor|需要.*重构|需要.*优化|需要.*改进|needs?\s+refactor", "refactor"),
        (r"需要.*analysis|需要.*分析|需要.*诊断|需要.*排查|needs?\s+analysis", "analysis"),
        (r"需要.*test|需要.*测试|需要.*验证|需要.*校验|needs?\s+test", "test"),
    ]

    # Known capabilities → agent mappings (extensible via registry)
    CAPABILITY_MAP: Dict[str, List[str]] = {
        "review": ["autoreview_reviewer", "reviewer"],
        "refactor": ["programmer_agent"],
        "analysis": ["architect_agent", "analyst"],
        "security": ["security_reviewer"],
        "test": ["qa_agent"],
    }

    def __init__(self):
        self._history: List[OrchestrationEvent] = []
        self._spawned_count: int = 0
        self._active_tasks: Dict[str, asyncio.Task] = {}

    async def sense_gap(
        self, agent_output: str, source_agent_id: str
    ) -> Optional[Dict[str, Any]]:
        """Detect if the agent output indicates it needs help.

        Returns dict with {capability, confidence, match} or None.
        """
        if not agent_output or len(agent_output) < 4:
            return None

        text = agent_output.lower()

        for pattern, capability in self.CAPABILITY_PATTERNS:
            match = re.search(pattern, text)
            if match:
                cap = capability
                candidates = self.CAPABILITY_MAP.get(cap, [])
                if candidates:
                    logger.debug(
                        "[orchestrator] sensed gap: %s → %s (agents: %s)",
                        cap, source_agent_id, candidates[:3],
                    )
                    return {
                        "capability": cap,
                        "confidence": 0.7,
                        "candidates": candidates,
                        "source_agent": source_agent_id,
                    }

        return None

    async def spawn(
        self,
        capability: str,
        task: str,
        session_id: str,
        *,
        source_agent_id: str = "",
        isolate_context: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Dynamically spawn a sub-agent for a detected capability gap.

        Returns dict with {target_agent, result_text, status} or None.
        """
        import uuid

        t0 = time.time()
        candidates = self.CAPABILITY_MAP.get(capability, [])
        if not candidates:
            return None

        target = candidates[0]  # Use best match (can be upgraded to scoring)
        event_id = f"orch-{uuid.uuid4().hex[:8]}"
        result_text = ""
        status = "failed"

        try:
            from core.apps.agents.subagent.coordinator import SubagentCoordinator
            coordinator = SubagentCoordinator()

            sub_result = await coordinator.execute_single(
                task=task,
                subagent_name=target,
                context=[{"role": "system", "content": f"Capability: {capability}\nSource: {source_agent_id}"}],
                isolate_context=isolate_context,
            )

            if sub_result and sub_result.output:
                result_text = str(sub_result.output)[:2000]
                status = "matched"
                self._spawned_count += 1
                logger.info(
                    "[orchestrator] spawned: %s → %s (capability=%s)",
                    source_agent_id, target, capability,
                )
            else:
                status = "failed"
                logger.warning(
                    "[orchestrator] spawn failed: %s → %s (no output)",
                    source_agent_id, target,
                )

        except Exception as e:
            logger.warning("[orchestrator] spawn error: %s", e)
            status = "failed"
            result_text = str(e)[:500]

        duration = int((time.time() - t0) * 1000)
        event = OrchestrationEvent(
            event_id=event_id,
            request_type="spawn",
            source_agent=source_agent_id,
            target_agent=target,
            capability=capability,
            status=status,
            duration_ms=duration,
        )
        self._history.append(event)

        return {
            "target_agent": target,
            "result_text": result_text,
            "status": status,
            "capability": capability,
            "event_id": event_id,
        }

    async def spawn_parallel(
        self,
        tasks: List[Dict[str, str]],
        session_id: str,
        *,
        source_agent_id: str = "",
        max_concurrent: int = 3,
    ) -> List[Optional[Dict[str, Any]]]:
        """Spawn multiple sub-agents in parallel for different capabilities.

        Each task dict: {capability, task_description}
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _bounded(cap: str, task: str):
            async with semaphore:
                return await self.spawn(
                    cap, task, session_id, source_agent_id=source_agent_id
                )

        coros = [_bounded(t["capability"], t["task"]) for t in tasks]
        results = await asyncio.gather(*coros, return_exceptions=True)
        return [r if not isinstance(r, Exception) else None for r in results]

    def get_capabilities(self) -> Dict[str, List[str]]:
        """List all registered capabilities and their available agents."""
        return dict(self.CAPABILITY_MAP)

    def stats(self) -> Dict[str, Any]:
        """Orchestration statistics."""
        return {
            "total_spawned": self._spawned_count,
            "total_events": len(self._history),
            "capabilities_registered": len(self.CAPABILITY_MAP),
            "recent_events": [e.to_dict() for e in self._history[-5:]],
            "capability_map": self.get_capabilities(),
        }


# ── Singleton ──

_orchestrator: Optional[DynamicOrchestrator] = None


def get_dynamic_orchestrator() -> DynamicOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = DynamicOrchestrator()
    return _orchestrator
