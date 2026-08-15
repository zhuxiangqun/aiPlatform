"""
Orchestration Layer — 企业AI平台统一编排层

三层架构:
  L1 Planning      (orchestration/):         IntentAnalyzer → ChainPlanner → CapabilityMapper → Orchestrator → DAG
  L2 Coordination  (harness/coordination/):  8 patterns: Pipeline, FanOut, Supervisor, ExpertPool, ProducerReviewer, Hierarchical
  L3 Execution     (harness/execution/ + apps/agents/): PipelineEngine, LangGraph, SubagentCoordinator, ParallelExecutor

Usage:
    from core.orchestration import Orchestrator, PipelinePattern, PipelineEngine
    # 一个 import 拿到全栈编排能力

    # 规划
    intent = analyze_intent(user_goal)
    plan = await Orchestrator().plan(intent)

    # 协调
    pattern = create_pattern("supervisor")

    # 执行
    engine = PipelineEngine(config)

约束:
  - L1 规划层 MUST be side-effect free: 仅产生计划/解释/DAG
  - L2 协调层 MUST NOT 直接执行工具: 工具调用必须通过 syscalls
  - L3 执行层 MUST 通过 ReActLoop 路径: 不得绕过 syscall 边界

设计文档: aiPlat-core/docs/orchestration/index.md
"""

# ── L1: Planning ──────────────────────────────────────────

from .orchestrator import Orchestrator
from .intent_analyzer import analyze_intent, StructuredIntent
from .chain_planner import plan_chain, ChainStep
from .capability_mapper import map_capabilities

# ── L2: Coordination ─────────────────────────────────────

from core.harness.coordination.patterns import (
    CoordinationContext,
    CoordinationResult,
    ICoordinationPattern,
    PipelinePattern,
    FanOutFanInPattern,
    ExpertPoolPattern,
    ProducerReviewerPattern,
    SupervisorPattern,
    HierarchicalDelegationPattern,
    create_pattern,
)

# ── L3: Execution ────────────────────────────────────────

from core.harness.execution.pipeline_engine import PipelineEngine
from core.apps.agents.subagent.coordinator import (
    SubagentCoordinator,
    get_subagent_coordinator,
)
from core.apps.agents.parallel_executor import ParallelExecutor

# ── Public API ───────────────────────────────────────────

__all__ = [
    # L1 — Planning
    "Orchestrator",
    "analyze_intent", "StructuredIntent",
    "plan_chain", "ChainStep",
    "map_capabilities",
    # L2 — Coordination
    "CoordinationContext", "CoordinationResult",
    "ICoordinationPattern",
    "PipelinePattern", "FanOutFanInPattern", "ExpertPoolPattern",
    "ProducerReviewerPattern", "SupervisorPattern",
    "HierarchicalDelegationPattern",
    "create_pattern",
    # L3 — Execution
    "PipelineEngine",
    "SubagentCoordinator", "get_subagent_coordinator",
    "ParallelExecutor",
]
