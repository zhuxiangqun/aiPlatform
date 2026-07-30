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
class RunContext:
    """Operational runtime context — bridges static ontology with dynamic business state.

    Injected by the API caller into system prompts so the LLM understands not just
    *what* an entity is (ontology), but *what's happening now* with it (runtime).

    Phase 10.1: caller-provided via API request body.
    Phase 10.2: auto-populated from GraphIndex entity traversal.
    Phase 10.3: real-time pull from DataSource connectors.

    Attributes:
        entity:      实体标识名，如 "注塑机#3"
        entity_type: 实体类型，如 "设备" / "订单" / "生产线"
        situation:   自由文本描述当前状态。建议格式: "主语+谓语+数值+单位"，
                     如 "温度215℃超限15℃, 当前在产加急订单B(交期今日18:00)"
        priority:    业务优先级 — normal / elevated / critical
        constraints: 约束条件列表，如 ["温控模块备件剩余2件", "维修部10分钟内可响应"]
        metadata:    扩展字段
    """
    entity: str = ""
    entity_type: str = ""
    situation: str = ""
    priority: str = ""
    time_range: str = ""          # P1-B: "2024Q3", "2024", "last_quarter" (standardized)
    current_page: str = ""        # UI page route, e.g. "/diagnostics/fde"
    current_page_label: str = ""  # UI page label, e.g. "FDE 工作台"
    current_page_group: str = ""  # UI sidebar group, e.g. "diagnostics"
    constraints: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_compact(self) -> str:
        """Compact serialization for system prompt injection. Target: ≤100 tokens."""
        parts = []
        if self.current_page_label:
            label_text = self.current_page_label
            if self.current_page_group:
                label_text = f"{label_text}"
            parts.append(f"用户当前页面: {label_text}")
        elif self.current_page:
            parts.append(f"用户当前页面路径: {self.current_page}")
        if self.entity:
            parts.append(f"当前{self.entity_type + ':' if self.entity_type else '实体:'} {self.entity}")
        elif self.entity_type and not self.current_page_label:
            parts.append(f"当前{self.entity_type}")
        if self.situation:
            parts.append(f"概况: {self.situation}")
        if self.priority:
            parts.append(f"优先级: {self.priority}")
        if self.time_range:
            parts.append(f"时间: {self.time_range}")
        if self.constraints:
            parts.append(f"约束: {'; '.join(self.constraints)}")
        return " | ".join(parts)


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

    @classmethod
    def from_dict(cls, data: Dict) -> DAG:
        return cls(
            explain=data.get("explain", ""),
            created_at=data.get("created_at", ""),
            nodes=[DAGNode(**n) for n in data.get("nodes", [])],
            metadata=data.get("metadata", {}),
        )


# ── Phase 20: Audit Trail types ──────────────────────────────────

@dataclass
class EvidenceFingerprint:
    """Locked evidence snapshot — immune to source document updates."""
    source_id: str = ""              # Document ID / sensor ID / API endpoint
    source_version: str = ""         # Document version number
    source_type: str = ""            # "wiki_page" | "kb_document" | "api_response" | "sensor_reading"
    snippet_hash: str = ""           # SHA256 hash for tamper-proof verification
    snippet_preview: str = ""        # First 100 chars for human inspection
    retrieved_at: str = ""           # ISO 8601 timestamp
    expiry_status: str = "valid"     # "valid" | "expired_30d" | "expired_90d" | "unknown"


@dataclass
class AuditStep:
    """Standardized reasoning step audit record — domain-agnostic."""
    step_id: int = 0
    parent_step_id: Optional[int] = None  # Parent step for recursive causal tracing

    # Provenance
    timestamp: str = ""              # ISO 8601
    agent: str = ""                  # Which Agent produced this
    domain: str = ""                 # Ontology domain
    session_id: str = ""
    tenant_id: str = ""

    # Reasoning
    trigger: str = ""                # Trigger condition (human-readable)
    rule_ref: str = ""               # Rule ID ("factory-ops.temperature.threshold")
    evidence: List[EvidenceFingerprint] = field(default_factory=list)

    # Conclusion
    conclusion: str = ""             # Inferred conclusion
    confidence: float = 0.0

    # Action
    action_triggered: str = ""       # Triggered operation
    action_target: str = ""          # Operation target
    action_result: str = ""          # "success" | "failed" | "pending"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "parent_step_id": self.parent_step_id,
            "timestamp": self.timestamp, "agent": self.agent, "domain": self.domain,
            "session_id": self.session_id, "tenant_id": self.tenant_id,
            "trigger": self.trigger, "rule_ref": self.rule_ref,
            "evidence": [{"source_id": e.source_id, "source_version": e.source_version,
                          "source_type": e.source_type, "snippet_hash": e.snippet_hash,
                          "snippet_preview": e.snippet_preview, "retrieved_at": e.retrieved_at,
                          "expiry_status": e.expiry_status} for e in self.evidence],
            "conclusion": self.conclusion, "confidence": self.confidence,
            "action_triggered": self.action_triggered, "action_target": self.action_target,
            "action_result": self.action_result,
        }


def _normalize_reasoning_path(raw: Any) -> List[Dict[str, Any]]:
    """Normalize heterogeneous Agent reasoning_path into uniform dict list.

    Supports: List[Dict] (standard), List[str], str, JSON string, None.
    """
    import json as _json

    if isinstance(raw, list) and all(isinstance(x, dict) for x in raw):
        return raw
    if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
        return [{"step": i + 1, "thought": x} for i, x in enumerate(raw)]
    if isinstance(raw, str):
        try:
            parsed = _json.loads(raw)
            return _normalize_reasoning_path(parsed)
        except (_json.JSONDecodeError, TypeError):
            return [{"step": 1, "thought": raw}]
    if raw is None:
        return []
    return [{"step": 1, "thought": str(raw)}]
