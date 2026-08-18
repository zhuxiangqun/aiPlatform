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
import os
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

    # Known capabilities → agent mappings (config-driven via AIPLAT_ROLE_AGENT_MAP env var).
    # Format: {"review": ["agent1", "agent2"], "analysis": ["agent3"], ...}
    # Falls back to empty dict if not configured — no agent IDs hardcoded in engine.
    _capability_map: Dict[str, List[str]]

    def __init__(self):
        import json as _json_om, os as _os_om
        self._history: List[OrchestrationEvent] = []
        self._spawned_count: int = 0
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._capability_map: Dict[str, List[str]] = {}
        raw = _os_om.getenv("AIPLAT_ROLE_AGENT_MAP", "")
        if raw:
            try:
                self._capability_map = _json_om.loads(raw)
            except Exception:
                self._capability_map = {}

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
                candidates = self._capability_map.get(cap, [])
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
        candidates = self._capability_map.get(capability, [])
        if not candidates:
            return None

        target = candidates[0]  # Use best match (can be upgraded to scoring)
        event_id = f"orch-{uuid.uuid4().hex[:8]}"
        result_text = ""
        status = "failed"

        try:
            from core.harness.integration import get_subagent_coordinator  # P0-A1: DI 解析
            coordinator = get_subagent_coordinator()

            # P1-A3: provider 选择 — AIPLAT_SUBAGENT_PROVIDER 配置外部 provider
            # (acp 等) 时走 provider 路径；默认 in_process 行为不变。
            provider = os.getenv("AIPLAT_SUBAGENT_PROVIDER", "in_process").strip().lower()
            if provider and provider != "in_process":
                sub_result = await coordinator.execute_with_provider(
                    task=task,
                    subagent_name=target,
                    context=[{"role": "system", "content": f"Capability: {capability}\nSource: {source_agent_id}"}],
                    provider=provider,
                )
            else:
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
        return dict(self._capability_map)

    async def decompose_task(
        self, complex_output: str, source_agent_id: str
    ) -> List[Dict[str, str]]:
        """Phase 35: LLM-based task decomposition.

        When agent output is complex (multi-domain), use LLM to break it into
        subtasks that can be handled by different sub-agents.

        Returns list of {capability, task_description} dicts.
        """
        if not complex_output or len(complex_output) < 20:
            return []

        try:
            from core.harness.syscalls import sys_llm_generate
            from core.harness.utils.model_injection import best_model_for_purpose, create_selected_adapter

            capabilities_str = ", ".join(self._capability_map.keys())
            prompt = f"""Break down the following agent output into subtasks that require
different capabilities. Available capabilities: {capabilities_str}.

Agent output:
{complex_output[:2000]}

For each subtask, output a JSON object:
{{"capability": "review|refactor|analysis|security|test", "task": "<subtask description>"}}

Return ONLY a JSON array of these objects. Maximum 5 subtasks."""

            model_name = best_model_for_purpose("code-gen")
            adapter = create_selected_adapter(model_name=model_name)
            if not adapter:
                return await self._heuristic_decompose(complex_output)

            result = await sys_llm_generate(
                adapter, prompt,
                trace_context={"source": "task_decompose", "agent": source_agent_id},
            )
            content = getattr(result, "content", str(result)) if result else ""

            # Parse JSON array from output
            import re as _re
            json_match = _re.search(r'\[.*\]', content, _re.DOTALL)
            if json_match:
                subtasks = json.loads(json_match.group())
                if isinstance(subtasks, list) and len(subtasks) > 0:
                    logger.info(
                        "[orchestrator] decomposed into %d subtasks", len(subtasks)
                    )
                    return subtasks

            return await self._heuristic_decompose(complex_output)
        except Exception as e:
            logger.debug("task decomposition failed: %s, falling back to heuristic", e)
            return await self._heuristic_decompose(complex_output)

    async def _heuristic_decompose(self, text: str) -> List[Dict[str, str]]:
        """Fallback: keyword-based decomposition without LLM."""
        subtasks = []
        lower = text.lower()

        # Simple keyword dispatch
        kw_map = {
            'review': r'review|审查|检查|审核',
            'refactor': r'refactor|重构|优化|改进',
            'analysis': r'analyz|分析|诊断|排查|investigat',
            'security': r'secur|安全|威胁|漏洞|vulnerab',
            'test': r'test|测试|验证|validate|verify',
        }

        for cap, pattern in kw_map.items():
            if re.search(pattern, lower):
                subtasks.append({
                    "capability": cap,
                    "task": f"Handle {cap} aspects of: {text[:200]}",
                })

        return subtasks[:3]  # max 3 heuristic subtasks

    async def execute_complex_task(
        self,
        complex_output: str,
        session_id: str,
        *,
        source_agent_id: str = "",
        max_concurrent: int = 3,
        swarm_mode: bool = False,  # Phase 37: Contract Net swarm
    ) -> List[Dict[str, Any]]:
        """Full pipeline — decompose + spawn + aggregate.

        Returns list of {capability, target_agent, result, status} per subtask.
        When swarm_mode=True, uses Contract Net Protocol (Phase 37).
        """
        if swarm_mode:
            try:
                from core.harness.coordination.swarm_broker import get_swarm_broker
                broker = get_swarm_broker()
                result = await broker.execute_swarm(
                    complex_output, session_id, source_agent_id=source_agent_id,
                )
                return [result] if result else []
            except Exception:
                logging.getLogger(__name__).debug('Swarm execution failed, falling through to standard decomposition', exc_info=True)

        subtasks = await self.decompose_task(complex_output, source_agent_id)
        if not subtasks:
            return []

        tasks = [
            {"capability": s["capability"], "task": s["task"]}
            for s in subtasks
        ]
        results = await self.spawn_parallel(
            tasks, session_id, source_agent_id=source_agent_id,
            max_concurrent=max_concurrent,
        )

        aggregated = []
        for i, r in enumerate(results):
            if r:
                aggregated.append({
                    "capability": subtasks[i]["capability"] if i < len(subtasks) else "unknown",
                    "target_agent": r.get("target_agent", ""),
                    "result": r.get("result_text", "")[:500],
                    "status": r.get("status", "failed"),
                })

        logger.info(
            "[orchestrator] complex task: %d subtasks → %d completed",
            len(subtasks), len(aggregated),
        )
        return aggregated

    def stats(self) -> Dict[str, Any]:
        """Orchestration statistics."""
        return {
            "total_spawned": self._spawned_count,
            "total_events": len(self._history),
            "capabilities_registered": len(self._capability_map),
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
