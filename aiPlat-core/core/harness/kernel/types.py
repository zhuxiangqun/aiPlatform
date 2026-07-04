"""
Kernel Types (Contracts) - Phase 9

This module defines the execution contracts used by HarnessIntegration.execute().
Expanded from Phase-1 minimal to full Phase 9 contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


ExecutionKind = Literal["agent", "skill", "tool", "graph"]
PlanStepKind = Literal["instruction", "tool", "skill", "llm"]
SpecLifecycle = Literal["draft", "review", "stable", "deprecated"]


@dataclass
class SpecContext:
    """
    FDE Spec lifecycle context — carries the spec's state into execution.

    EngineRouter uses this for plan-aware routing:
      - draft → experimental routing (fast engines, low-cost models)
      - stable → production routing (full gate enforcement)
      - deprecated → warn + suggest migration
    """
    spec_id: str = ""
    spec_version: str = ""
    lifecycle_state: SpecLifecycle = "draft"
    quality_score: float = 0.0
    promote_ready: bool = False
    review_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlanStep:
    step: int
    action: str
    kind: PlanStepKind = "instruction"
    args: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"


@dataclass
class ExecutionPlan:
    version: str = "9.0"
    explain: str = ""
    steps: List[PlanStep] = field(default_factory=list)
    current_step: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    dag: Optional[dict] = None  # Phase 9: DAG topology for plan-aware routing
    spec: Optional[SpecContext] = None  # Phase 9: FDE Spec lifecycle context

    @property
    def current(self) -> Optional[PlanStep]:
        if 0 <= self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None

    @property
    def remaining(self) -> List[PlanStep]:
        return self.steps[self.current_step + 1:]

    def advance(self) -> Optional[PlanStep]:
        if self.current and self.current.status != "completed":
            self.current.status = "completed"
        self.current_step += 1
        return self.current

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "explain": self.explain,
            "current_step": self.current_step,
            "steps": [
                {
                    "step": s.step,
                    "action": s.action,
                    "kind": s.kind,
                    "args": s.args or {},
                    "status": s.status,
                }
                for s in self.steps
            ],
            "metadata": self.metadata or {},
        }


@dataclass
class ExecutionRequest:
    """Kernel execution request."""

    kind: ExecutionKind
    target_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    user_id: str = "system"
    session_id: str = "default"
    request_id: Optional[str] = None
    run_id: Optional[str] = None
    execution_plan: Optional[ExecutionPlan] = None


@dataclass
class ExecutionResult:
    """Kernel execution result."""

    ok: bool
    payload: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    error_detail: Optional[Dict[str, Any]] = None
    http_status: int = 200
    trace_id: Optional[str] = None
    run_id: Optional[str] = None


# ── DAG Types (Phase 10 — orchestrated pipeline execution) ──

@dataclass
class DAGNode:
    """A single node in a directed acyclic execution graph."""
    id: str
    role: str = ""          # generic role label (config-driven via AGENT.md)
    agent_id: str = ""      # matched agent from registry or capability mapper
    depends_on: List[str] = field(default_factory=list)  # node IDs this depends on
    execution_mode: str = "code_first"  # "code_first" | "tdd" | "plan_only"
    review_gate: str = "none"         # "none" | "quick" | "llm" | "hitl"
    tdd_enforce: bool = False
    context_isolation: str = "shared" # "shared" | "isolated"
    status: str = "pending"           # pending | executing | completed | failed | skipped


@dataclass
class DAG:
    """Directed acyclic execution graph."""
    nodes: List[DAGNode] = field(default_factory=list)
    explain: str = ""
    created_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def topological_order(self) -> List[List[DAGNode]]:
        """Return layers of nodes that can execute in parallel."""
        indeg: Dict[str, int] = {n.id: 0 for n in self.nodes}
        out_edges: Dict[str, List[str]] = {n.id: [] for n in self.nodes}
        for n in self.nodes:
            for dep in n.depends_on:
                if dep in indeg:
                    indeg[n.id] += 1
                    out_edges[dep].append(n.id)
        layers: List[List[DAGNode]] = []
        ready = {n.id for n in self.nodes if indeg[n.id] == 0}
        visited: set = set()
        while ready:
            layer = [n for n in self.nodes if n.id in ready and n.id not in visited]
            layers.append(layer)
            visited.update(ready)
            next_ready: set = set()
            for nid in ready:
                for out_id in out_edges.get(nid, []):
                    indeg[out_id] -= 1
                    if indeg[out_id] == 0:
                        next_ready.add(out_id)
            ready = next_ready
        return layers

    def to_dict(self) -> Dict[str, Any]:
        return {
            "explain": self.explain,
            "created_at": self.created_at,
            "nodes": [{"id": n.id, "role": n.role, "agent_id": n.agent_id,
                        "depends_on": n.depends_on, "execution_mode": n.execution_mode,
                        "review_gate": n.review_gate, "tdd_enforce": n.tdd_enforce,
                        "context_isolation": n.context_isolation} for n in self.nodes],
            "metadata": self.metadata,
        }
