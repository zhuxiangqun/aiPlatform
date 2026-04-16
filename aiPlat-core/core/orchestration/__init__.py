"""
Orchestration layer (Phase 5.2).

Constraints:
- Orchestrator MUST be side-effect free: only produces a plan/explain output.
- Tool/Skill execution must never happen here; it must happen via syscalls in engines/loops.

Phase 5.2 minimal:
- Add Orchestrator that produces a JSON plan using sys_llm_generate (best-effort).
- Integrate behind an env flag in HarnessIntegration.
"""

from .orchestrator import Orchestrator, OrchestratorPlan, PlanStep

__all__ = ["Orchestrator", "OrchestratorPlan", "PlanStep"]

