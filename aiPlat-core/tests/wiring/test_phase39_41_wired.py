"""
Wiring tests for Phase 39-41 L6 modules.

Verifies each new module has at least 1 production code caller (non-test, non-self).
Pattern: import the module, then check for production callers via grep.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
CORE_DIR = os.path.join(REPO_ROOT, "core")


def _has_caller(module_path: str, class_or_func_name: str) -> bool:
    """Check if a symbol has production callers outside its own file and tests."""
    result = subprocess.run(
        [
            "grep", "-rl", class_or_func_name,
            "--include=*.py",
            CORE_DIR,
        ],
        capture_output=True, text=True, timeout=10,
    )
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        rel = os.path.relpath(line.strip(), REPO_ROOT)
        if "tests/" in rel:
            continue
        if "__pycache__" in rel:
            continue
        if module_path in rel:
            continue
        return True
    return False


# ══════════════════════════════════════════════════
# Phase 39: Abstract Goal Decomposition
# ══════════════════════════════════════════════════


def test_abstract_goal_decomposer_has_callers():
    """AbstractGoalDecomposer wired into GoalGenerator, GoalExecutor, WakeScheduler."""
    assert _has_caller(
        "abstract_goal_decomposer.py", "get_abstract_goal_decomposer"
    ), "AbstractGoalDecomposer has 0 production callers"


def test_goal_dependency_graph_has_callers():
    """GoalDependencyGraph wired into GoalExecutor, WakeScheduler."""
    assert _has_caller(
        "goal_dependency_graph.py", "get_goal_dependency_graph"
    ), "GoalDependencyGraph has 0 production callers"


def test_goal_progress_evaluator_has_callers():
    """GoalProgressEvaluator wired into GoalExecutor."""
    assert _has_caller(
        "goal_progress_evaluator.py", "get_goal_progress_evaluator"
    ), "GoalProgressEvaluator has 0 production callers"


# ══════════════════════════════════════════════════
# Phase 40: Auto Deploy
# ══════════════════════════════════════════════════


def test_deploy_engine_has_callers():
    """DeployEngine wired into GoalExecutor, ToolBootstrap."""
    assert _has_caller(
        "deploy_engine.py", "get_deploy_engine"
    ), "DeployEngine has 0 production callers"


def test_git_pusher_has_callers():
    """GitPusher wired into DeployEngine."""
    assert _has_caller(
        "git_pusher.py", "GitPusher"
    ), "GitPusher has 0 production callers"


# ══════════════════════════════════════════════════
# Phase 41: External Discovery
# ══════════════════════════════════════════════════


def test_discovery_listener_has_callers():
    """DiscoveryListener wired into server.py startup."""
    assert _has_caller(
        "discovery_listener.py", "get_discovery_listener"
    ), "DiscoveryListener has 0 production callers"


def test_auto_register_has_callers():
    """AutoRegisterEngine wired into DiscoveryListener."""
    assert _has_caller(
        "auto_register.py", "get_auto_register_engine"
    ), "AutoRegisterEngine has 0 production callers"


# ══════════════════════════════════════════════════
# Module importability (smoke tests)
# ══════════════════════════════════════════════════


def test_abstract_goal_decomposer_importable():
    from core.harness.optimization.abstract_goal_decomposer import (
        AbstractGoalDecomposer, DecomposeResult, get_abstract_goal_decomposer,
    )
    assert AbstractGoalDecomposer is not None
    assert DecomposeResult is not None
    assert get_abstract_goal_decomposer() is not None


def test_goal_dependency_graph_importable():
    from core.harness.optimization.goal_dependency_graph import (
        GoalDependencyGraph, ExecutionPlan, get_goal_dependency_graph,
    )
    assert GoalDependencyGraph is not None
    assert ExecutionPlan is not None
    graph = get_goal_dependency_graph()
    assert graph is not None


def test_goal_progress_evaluator_importable():
    from core.harness.optimization.goal_progress_evaluator import (
        GoalProgressEvaluator, ProgressReport, get_goal_progress_evaluator,
    )
    assert GoalProgressEvaluator is not None
    evaluator = get_goal_progress_evaluator()
    assert evaluator is not None
    report = evaluator.evaluate("test", [], 0)
    assert report.trend in ("completed", "unknown", "plateau", "converging", "diverging")


def test_deploy_engine_importable():
    from core.harness.deployment.deploy_engine import (
        DeployEngine, DeployResult, get_deploy_engine,
    )
    assert DeployEngine is not None
    engine = get_deploy_engine()
    assert engine is not None
    assert isinstance(engine.enabled, bool)


def test_git_pusher_importable():
    from core.harness.deployment.git_pusher import GitPusher, PushResult
    assert GitPusher is not None


def test_discovery_listener_importable():
    from core.harness.infrastructure.discovery_listener import (
        DiscoveryListener, get_discovery_listener,
    )
    assert DiscoveryListener is not None
    listener = get_discovery_listener()
    assert listener is not None


def test_auto_register_importable():
    from core.harness.infrastructure.auto_register import (
        AutoRegisterEngine, AutoRegisterResult, get_auto_register_engine,
    )
    assert AutoRegisterEngine is not None
    engine = get_auto_register_engine()
    assert engine is not None


# ══════════════════════════════════════════════════
# Business Objective type in GoalGenerator
# ══════════════════════════════════════════════════


def test_business_objective_goal_type_exists():
    from core.harness.optimization.goal_generator import GoalType, get_goal_generator
    assert GoalType.BUSINESS_OBJECTIVE.value == "business_objective"
    gen = get_goal_generator()
    goals = gen.generate()
    assert isinstance(goals, list)
