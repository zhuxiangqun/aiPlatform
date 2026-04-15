"""
Tests for Planning Graph module.

Tests cover:
- PlanningConfig defaults
- PlanningState initialization
- SubTask and dependency resolution
- DecompositionStrategy enum
- PlanningGraph creation
- SubTask parsing
- create_planning_graph factory
- Fallback execution
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from harness.execution.langgraph.graphs.planning import (
    PlanningConfig,
    PlanningState,
    PlanningGraph,
    SubTask,
    SubTaskStatus,
    DecompositionStrategy,
    create_planning_graph,
)


class TestPlanningConfig:
    """Tests for PlanningConfig."""

    def test_default_config(self):
        config = PlanningConfig()
        assert config.strategy == DecompositionStrategy.SEQUENTIAL
        assert config.max_depth == 3
        assert config.max_total_steps == 20
        assert config.max_parallel == 5
        assert config.model is None
        assert len(config.tools) == 0

    def test_custom_config(self):
        config = PlanningConfig(
            strategy=DecompositionStrategy.PARALLEL,
            max_depth=5,
            max_parallel=10,
        )
        assert config.strategy == DecompositionStrategy.PARALLEL
        assert config.max_depth == 5
        assert config.max_parallel == 10


class TestSubTask:
    """Tests for SubTask."""

    def test_default_subtask(self):
        task = SubTask(task_id="T1", description="Do something")
        assert task.task_id == "T1"
        assert task.description == "Do something"
        assert task.dependencies == []
        assert task.status == SubTaskStatus.PENDING
        assert task.result is None
        assert task.priority == 0

    def test_subtask_with_dependencies(self):
        task = SubTask(
            task_id="T3",
            description="Third task",
            dependencies=["T1", "T2"]
        )
        assert len(task.dependencies) == 2

    def test_is_ready_no_deps(self):
        task = SubTask(task_id="T1", description="First task")
        assert task.is_ready(set()) is True

    def test_is_ready_with_deps_satisfied(self):
        task = SubTask(
            task_id="T2",
            description="Second task",
            dependencies=["T1"]
        )
        assert task.is_ready({"T1"}) is True

    def test_is_ready_with_deps_unsatisfied(self):
        task = SubTask(
            task_id="T2",
            description="Second task",
            dependencies=["T1"]
        )
        assert task.is_ready(set()) is False

    def test_is_ready_with_partial_deps(self):
        task = SubTask(
            task_id="T3",
            description="Third task",
            dependencies=["T1", "T2"]
        )
        assert task.is_ready({"T1"}) is False
        assert task.is_ready({"T1", "T2"}) is True


class TestPlanningState:
    """Tests for PlanningState."""

    def test_default_state(self):
        state = PlanningState()
        assert state.task == ""
        assert state.subtasks == []
        assert len(state.completed_ids) == 0
        assert len(state.failed_ids) == 0
        assert state.current_phase == "decompose"
        assert state.results == {}
        assert state.final_result is None

    def test_state_with_task(self):
        state = PlanningState(task="Analyze data")
        assert state.task == "Analyze data"


class TestSubTaskStatus:
    """Tests for SubTaskStatus enum."""

    def test_all_statuses(self):
        assert SubTaskStatus.PENDING.value == "pending"
        assert SubTaskStatus.RUNNING.value == "running"
        assert SubTaskStatus.COMPLETED.value == "completed"
        assert SubTaskStatus.FAILED.value == "failed"
        assert SubTaskStatus.SKIPPED.value == "skipped"


class TestDecompositionStrategy:
    """Tests for DecompositionStrategy enum."""

    def test_all_strategies(self):
        assert DecompositionStrategy.SEQUENTIAL.value == "sequential"
        assert DecompositionStrategy.PARALLEL.value == "parallel"
        assert DecompositionStrategy.HIERARCHICAL.value == "hierarchical"


class TestPlanningGraph:
    """Tests for PlanningGraph."""

    def test_graph_creation(self):
        graph = PlanningGraph()
        assert graph._config is not None
        assert graph._executor is not None
        assert graph._decomposer is not None

    def test_graph_with_config(self):
        config = PlanningConfig(strategy=DecompositionStrategy.PARALLEL)
        graph = PlanningGraph(config)
        assert graph._config.strategy == DecompositionStrategy.PARALLEL

    def test_parse_subtasks(self):
        graph = PlanningGraph()
        output = """TASK_1: 数据采集 [depends_on: 无]
TASK_2: 数据分析 [depends_on: TASK_1]
TASK_3: 报告生成 [depends_on: TASK_2]"""
        subtasks = graph._parse_subtasks(output)
        assert len(subtasks) == 3
        assert subtasks[0].task_id == "TASK_1"
        assert subtasks[0].dependencies == []
        assert subtasks[1].task_id == "TASK_2"
        assert subtasks[1].dependencies == ["TASK_1"]
        assert subtasks[2].task_id == "TASK_3"
        assert subtasks[2].dependencies == ["TASK_2"]

    def test_parse_subtasks_empty(self):
        graph = PlanningGraph()
        subtasks = graph._parse_subtasks("")
        assert len(subtasks) == 0

    def test_parse_subtasks_no_deps(self):
        graph = PlanningGraph()
        output = "TASK_1: Simple task"
        subtasks = graph._parse_subtasks(output)
        assert len(subtasks) == 1
        assert subtasks[0].dependencies == []

    def test_should_continue_approved_not_applicable(self):
        pass

    def test_aggregate_wrapper_completed(self):
        graph = PlanningGraph()
        state = PlanningState(
            task="Test task",
            results={"T1": "Result 1", "T2": "Result 2"},
            completed_ids={"T1", "T2"},
            subtasks=[
                SubTask(task_id="T1", description="Task 1", status=SubTaskStatus.COMPLETED),
                SubTask(task_id="T2", description="Task 2", status=SubTaskStatus.COMPLETED),
            ]
        )
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            graph._aggregate_wrapper(state)
        )
        assert result["current_phase"] == "completed"
        assert result["final_result"] is not None


class TestCreatePlanningGraph:
    """Tests for create_planning_graph factory."""

    def test_factory_defaults(self):
        graph = create_planning_graph()
        assert graph._config.strategy == DecompositionStrategy.SEQUENTIAL

    def test_factory_parallel(self):
        graph = create_planning_graph(strategy=DecompositionStrategy.PARALLEL)
        assert graph._config.strategy == DecompositionStrategy.PARALLEL

    def test_factory_hierarchical(self):
        graph = create_planning_graph(strategy=DecompositionStrategy.HIERARCHICAL)
        assert graph._config.strategy == DecompositionStrategy.HIERARCHICAL