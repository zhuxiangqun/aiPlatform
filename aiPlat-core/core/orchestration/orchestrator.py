"""
Orchestrator (Phase 10 — full chain planning + DAG generation).

Upgraded from Phase 9: now supports intent analysis, thinking chain generation,
capability-to-agent mapping, and DAG output for PipelineEngine consumption.

Design:
- Input: user intent text (natural language)
- Process: analyze_intent → plan_chain → map_capabilities → build_dag
- Output: DAG (directed acyclic graph of execution nodes)

Side-effect free per docs/design/kernel_orchestrator/04-security-and-audit.md.
"""
from __future__ import annotations
import logging

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.harness.kernel.types import DAG, DAGNode, ExecutionPlan, PlanStep as KernelPlanStep
from .intent_analyzer import analyze_intent, StructuredIntent
from .chain_planner import plan_chain, ChainStep
from .capability_mapper import map_capabilities


@dataclass
class PlanStep:
    """A single plan step (machine-friendly)."""
    step: int
    action: str
    kind: str = "instruction"  # instruction|tool|skill|llm
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestratorPlan:
    """Orchestrator output — now with DAG support."""
    version: str = "10.0"
    explain: str = ""
    steps: List[PlanStep] = field(default_factory=list)
    dag: Optional[DAG] = None
    created_at: float = field(default_factory=lambda: time.time())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "version": self.version,
            "explain": self.explain,
            "created_at": self.created_at,
            "steps": [
                {"step": s.step, "action": s.action, "kind": s.kind, "args": s.args or {}}
                for s in self.steps
            ],
            "metadata": self.metadata or {},
        }
        if self.dag:
            result["dag"] = self.dag.to_dict()
        return result

    def to_execution_plan(self) -> ExecutionPlan:
        return ExecutionPlan(
            version=self.version,
            explain=self.explain,
            steps=[
                KernelPlanStep(
                    step=s.step, action=s.action,
                    kind=s.kind,  # type: ignore[arg-type]
                    args=s.args,
                )
                for s in self.steps
            ],
            metadata=self.metadata or {},
        )


class Orchestrator:
    """Phase 10 orchestrator — intent → chain → capabilities → DAG."""

    async def plan_intent(self, *, intent_text: str, model: Any = None) -> OrchestratorPlan:
        """Full planning pipeline: intent analysis → chain → capabilities → DAG."""
        # Step 1: Analyze intent
        intent = analyze_intent(intent_text)

        # Step 2: Generate thinking chain
        chain = await plan_chain(intent, model=model)

        # Step 3: Map capabilities to agents
        agent_map = await map_capabilities(chain, model=model)

        # Step 4: Build DAG with execution modes
        dag = self._build_dag(intent, chain, agent_map)

        # Step 5: Generate step plan (legacy format for backward compat)
        steps = self._chain_to_steps(chain)

        explain = (
            f"领域: {intent.domain}, 复杂度: {intent.complexity}, "
            f"阶段: {' → '.join(f'{s.role}({agent_map.get(s.id, s.id)})' for s in chain)}"
        )

        return OrchestratorPlan(
            explain=explain,
            steps=steps,
            dag=dag,
            metadata={
                "intent": intent.to_dict(),
                "agent_map": agent_map,
                "chain": [{"id": s.id, "role": s.role, "depends_on": s.depends_on} for s in chain],
            },
        )

    def _build_dag(self, intent: StructuredIntent, chain: List[ChainStep], agent_map: Dict[str, str]) -> DAG:
        """Construct DAG from chain and agent mapping."""
        complexity = intent.complexity
        nodes = []

        # Config-driven role→mode mapping (AIPLAT_DAG_ROLE_MODES env var, JSON)
        role_modes: Dict[str, str] = {}
        try:
            raw = os.getenv("AIPLAT_DAG_ROLE_MODES", "")
            if raw:
                role_modes = json.loads(raw)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        # Config-driven role→gate mapping (AIPLAT_DAG_ROLE_GATES env var, JSON)
        role_gates: Dict[str, str] = {}
        try:
            raw = os.getenv("AIPLAT_DAG_ROLE_GATES", "")
            if raw:
                role_gates = json.loads(raw)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        for step in chain:
            agent_id = agent_map.get(step.id, step.id)
            step_role = (step.role or "").strip()
            # Execution mode: config-driven role→mode lookup
            mode = role_modes.get(step_role, "code_first")
            # Review gate: config-driven role→gate lookup
            gate = role_gates.get(step_role, "none")
            # Complexity override: upgrade gate level for high-complexity
            if complexity == "high" and gate in ("quick", "none"):
                gate = "llm"

            nodes.append(DAGNode(
                id=step.id,
                role=step.role,
                agent_id=agent_id,
                depends_on=list(step.depends_on),
                execution_mode=mode,
                review_gate=gate,
                tdd_enforce=(mode == "tdd"),
                context_isolation="isolated" if complexity == "high" else "shared",
            ))
        return DAG(
            nodes=nodes,
            explain=f"Auto-generated DAG for {intent.domain} (complexity={complexity})",
            created_at=time.time(),
            metadata={"intent": intent.to_dict()},
        )

    def _chain_to_steps(self, chain: List[ChainStep]) -> List[PlanStep]:
        """Convert chain to legacy step format for backward compatibility."""
        return [
            PlanStep(step=i + 1, kind="skill", action=s.id,
                     args={"role": s.role, "depends_on": s.depends_on})
            for i, s in enumerate(chain)
        ]

    # ── Legacy API (kept for Harness integration backward compat) ──

    async def plan(
        self, *, agent_id: str, model: Any, messages: List[Dict[str, str]],
        context: Optional[Dict[str, Any]] = None,
        trace_context: Optional[Dict[str, Any]] = None,
    ) -> OrchestratorPlan:
        """Legacy plan() — delegates to plan_intent using last message as intent.
        Kept for backward compatibility with integration.py's _execute_agent()."""
        task = ""
        if messages:
            task = str(messages[-1].get("content", "") or "")
        if not task:
            return OrchestratorPlan(
                explain="No task to plan",
                steps=[
                    PlanStep(step=1, kind="instruction", action="理解任务与约束"),
                    PlanStep(step=2, kind="instruction", action="按既有 LoopEngine 执行"),
                ],
            )
        try:
            return await self.plan_intent(intent_text=task, model=model)
        except Exception:
            return OrchestratorPlan(
                explain="Fallback plan",
                steps=[PlanStep(step=1, kind="instruction", action="按既有 LoopEngine 执行")],
                metadata={"fallback": True},
            )
