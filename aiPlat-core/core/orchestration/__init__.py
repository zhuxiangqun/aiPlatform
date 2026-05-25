"""
Orchestration layer (Phase 10).

Upgraded from Phase 5.2: now includes intent analysis, thinking chain generation,
capability-to-agent mapping, and DAG construction for PipelineEngine consumption.

Constraints:
- Orchestrator MUST be side-effect free: only produces a plan/explain/DAG output.
- Tool/Skill execution must never happen here; it must happen via syscalls in engines/loops.
"""
from .orchestrator import Orchestrator, OrchestratorPlan, PlanStep
from .intent_analyzer import analyze_intent, StructuredIntent
from .chain_planner import plan_chain, ChainStep
from .capability_mapper import map_capabilities

__all__ = [
    "Orchestrator", "OrchestratorPlan", "PlanStep",
    "analyze_intent", "StructuredIntent",
    "plan_chain", "ChainStep",
    "map_capabilities",
]
