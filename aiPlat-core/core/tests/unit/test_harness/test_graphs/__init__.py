"""
Tests for Reflection Graph module.

Tests cover:
- ReflectionConfig defaults
- ReflectionState initialization
- ReflectionGraph creation
- CriticResult parsing
- EvaluationDimension thresholds
- create_reflection_graph factory
- Fallback execution flow
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from harness.execution.langgraph.graphs.reflection import (
    ReflectionConfig,
    ReflectionState,
    ReflectionStatus,
    ReflectionGraph,
    CriticResult,
    EvaluationDimension,
    create_reflection_graph,
)


class TestReflectionConfig:
    """Tests for ReflectionConfig."""

    def test_default_config(self):
        config = ReflectionConfig()
        assert config.max_iterations == 3
        assert config.pass_keyword == "PASS"
        assert config.executor_model is None
        assert config.critic_model is None
        assert len(config.evaluation_dimensions) == 4
        assert len(config.tools) == 0

    def test_custom_config(self):
        config = ReflectionConfig(
            max_iterations=5,
            pass_keyword="APPROVED",
            evaluation_dimensions=[EvaluationDimension.FACTUALITY, EvaluationDimension.CLARITY],
            dimension_thresholds={
                EvaluationDimension.FACTUALITY: 0.9,
                EvaluationDimension.CLARITY: 0.8,
            }
        )
        assert config.max_iterations == 5
        assert config.pass_keyword == "APPROVED"
        assert len(config.evaluation_dimensions) == 2

    def test_dimension_thresholds_defaults(self):
        config = ReflectionConfig()
        assert config.dimension_thresholds[EvaluationDimension.FACTUALITY] == 0.8
        assert config.dimension_thresholds[EvaluationDimension.COMPLETENESS] == 0.7
        assert config.dimension_thresholds[EvaluationDimension.CLARITY] == 0.7
        assert config.dimension_thresholds[EvaluationDimension.FORMAT] == 0.8


class TestReflectionState:
    """Tests for ReflectionState."""

    def test_default_state(self):
        state = ReflectionState()
        assert state.task == ""
        assert state.executor_output == ""
        assert state.critic_result is None
        assert state.iteration == 0
        assert state.status == ReflectionStatus.PENDING
        assert state.history == []
        assert state.final_output is None

    def test_state_with_task(self):
        state = ReflectionState(task="Write a summary")
        assert state.task == "Write a summary"


class TestCriticResult:
    """Tests for CriticResult."""

    def test_default_result(self):
        result = CriticResult()
        assert result.passed is False
        assert result.dimensions == {}
        assert result.feedback == []
        assert result.summary == ""

    def test_passed_result(self):
        result = CriticResult(
            passed=True,
            dimensions={EvaluationDimension.FACTUALITY: 0.9},
            summary="Good quality"
        )
        assert result.passed is True
        assert result.dimensions[EvaluationDimension.FACTUALITY] == 0.9


class TestReflectionGraph:
    """Tests for ReflectionGraph."""

    def test_graph_creation(self):
        graph = ReflectionGraph()
        assert graph._config is not None
        assert graph._executor is not None
        assert graph._critic is not None

    def test_graph_with_config(self):
        config = ReflectionConfig(max_iterations=5)
        graph = ReflectionGraph(config)
        assert graph._config.max_iterations == 5

    def test_parse_critic_result_pass(self):
        graph = ReflectionGraph()
        output = "STATUS: PASS\nSCORES: factuality=0.9 completeness=0.8 clarity=0.9 format=0.85\nFEEDBACK: None"
        result = graph._parse_critic_result(output)
        assert result.passed is True

    def test_parse_critic_result_rejected(self):
        graph = ReflectionGraph()
        output = "STATUS: REJECTED\nSCORES: factuality=0.5 completeness=0.6 clarity=0.9 format=0.85\nFEEDBACK:\n- Improve factual accuracy\n- Add more details"
        result = graph._parse_critic_result(output)
        assert result.passed is False
        assert len(result.feedback) >= 1

    def test_should_continue_approved(self):
        graph = ReflectionGraph()
        state = ReflectionState(status=ReflectionStatus.APPROVED)
        result = graph._should_continue(state)
        assert result == "finish"

    def test_should_continue_max_iterations(self):
        config = ReflectionConfig(max_iterations=3)
        graph = ReflectionGraph(config)
        state = ReflectionState(iteration=3)
        result = graph._should_continue(state)
        assert result == "finish"

    def test_should_continue_not_done(self):
        graph = ReflectionGraph()
        state = ReflectionState(
            iteration=1,
            critic_result=CriticResult(passed=False, feedback=["Improve quality"])
        )
        result = graph._should_continue(state)
        assert result == "continue"

    def test_build_critic_prompt_initial(self):
        graph = ReflectionGraph()
        prompt = graph._build_critic_prompt("Write code", "print('hello')", [])
        assert "Write code" in prompt
        assert "print('hello')" in prompt
        assert "PASS" in prompt

    def test_build_critic_prompt_with_feedback(self):
        graph = ReflectionGraph()
        prompt = graph._build_critic_prompt(
            "Write code", "print('hello')", ["Add error handling"]
        )
        assert "Add error handling" in prompt

    def test_build_executor_prompt_initial(self):
        graph = ReflectionGraph()
        prompt = graph._build_executor_prompt("Write code", "", [])
        assert "Write code" in prompt

    def test_build_executor_prompt_with_feedback(self):
        graph = ReflectionGraph()
        prompt = graph._build_executor_prompt(
            "Write code", "print('hello')", ["Add error handling"]
        )
        assert "Add error handling" in prompt
        assert "print('hello')" in prompt


class TestCreateReflectionGraph:
    """Tests for create_reflection_graph factory."""

    def test_factory_defaults(self):
        graph = create_reflection_graph()
        assert graph._config.max_iterations == 3

    def test_factory_custom(self):
        graph = create_reflection_graph(max_iterations=5)
        assert graph._config.max_iterations == 5

    def test_factory_custom_dimensions(self):
        dimensions = [EvaluationDimension.FACTUALITY, EvaluationDimension.CLARITY]
        thresholds = {
            EvaluationDimension.FACTUALITY: 0.9,
            EvaluationDimension.CLARITY: 0.8,
        }
        graph = create_reflection_graph(
            evaluation_dimensions=dimensions,
            dimension_thresholds=thresholds
        )
        assert len(graph._config.evaluation_dimensions) == 2
        assert graph._config.dimension_thresholds[EvaluationDimension.FACTUALITY] == 0.9


class TestEvaluationDimension:
    """Tests for EvaluationDimension enum."""

    def test_all_dimensions(self):
        assert EvaluationDimension.FACTUALITY.value == "factuality"
        assert EvaluationDimension.COMPLETENESS.value == "completeness"
        assert EvaluationDimension.CLARITY.value == "clarity"
        assert EvaluationDimension.FORMAT.value == "format"

    def test_dimension_count(self):
        assert len(EvaluationDimension) == 4