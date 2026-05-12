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


@dataclass
class PlanStep:
    step: int
    action: str
    kind: PlanStepKind = "instruction"
    args: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending|in_progress|completed|skipped|failed


@dataclass
class ExecutionPlan:
    version: str = "9.0"
    explain: str = ""
    steps: List[PlanStep] = field(default_factory=list)
    current_step: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

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
