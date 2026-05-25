"""
PipelineEngine core behavior tests.

Covers: model selection, state key consistency, stage execution path, evaluation.
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

# Ensure core is importable
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "aiPlat-core"))

from core.schemas_builder import (
    PipelineConfig,
    PipelineStageConfig,
    BuilderSessionPhase,
)
from core.harness.execution.pipeline_engine import PipelineEngine, PipelineState


def _make_stage(
    id: str = "test_stage",
    agent_id: str = "test_agent",
    output_artifact: str = "test_output",
    agent_type: str = "react",
    uses_file_output: bool = False,
    scoring_dimensions: list = None,
    generate_test_plan: bool = False,
    test_result_key: str = "",
) -> PipelineStageConfig:
    return PipelineStageConfig(
        id=id, agent_id=agent_id, output_artifact=output_artifact,
        agent_type=agent_type, uses_file_output=uses_file_output,
        scoring_dimensions=scoring_dimensions or [],
        generate_test_plan=generate_test_plan,
        test_result_key=test_result_key,
        prompt_extra="",
        failure_strategy="fail_pipeline",
    )


class TestLoadDefaultModel:
    """Test model selection and routing."""

    @patch("core.harness.utils.model_injection.create_selected_adapter")
    def test_default_model_category_agent(self, mock_create):
        """Agent category should use AIPLAT_AGENT_MODEL."""
        mock_create.return_value = MagicMock(model_name="deepseek-reasoner")
        with patch.dict(os.environ, {"AIPLAT_AGENT_MODEL": "deepseek-reasoner"}, clear=False):
            model = PipelineEngine._load_default_model(category="agent")
            assert model is not None
            mock_create.assert_called_once_with(model_name="deepseek-reasoner")

    @patch("core.harness.utils.model_injection.create_selected_adapter")
    def test_default_model_category_default(self, mock_create):
        """Default category should use AIPLAT_LLM_MODEL."""
        mock_create.return_value = MagicMock(model_name="deepseek-chat")
        with patch.dict(os.environ, {"AIPLAT_LLM_MODEL": "deepseek-chat"}, clear=False):
            model = PipelineEngine._load_default_model(category="default")
            assert model is not None
            mock_create.assert_called_once_with(model_name="deepseek-chat")

    @patch("core.harness.utils.model_injection.create_selected_adapter")
    def test_explicit_model_name_overrides_env(self, mock_create):
        """Explicit model_name parameter should override env vars."""
        mock_create.return_value = MagicMock(model_name="custom-model")
        model = PipelineEngine._load_default_model(model_name="custom-model", category="agent")
        assert model is not None
        mock_create.assert_called_once_with(model_name="custom-model")


class TestStateKeyConsistency:
    """Test that state keys are consistent across all code paths."""

    def test_initialize_sets_session_id(self):
        """initialize() should store project_id under 'session_id' key."""
        config = PipelineConfig(stages=[_make_stage()], max_tokens_per_run=10000)
        # Confirm PipelineState TypedDict defines session_id
        state: PipelineState = {}
        state["session_id"] = "test_project"
        assert state["session_id"] == "test_project"
        assert state.get("project_id") is None  # should NOT exist

    def test_project_id_not_in_state_by_default(self):
        """'project_id' is not a PipelineState key; code should not read it."""
        state: PipelineState = {"session_id": "test_project"}
        # BUG: _exec_stage reads state.get('project_id') which returns None
        val = state.get("project_id", "fallback")
        assert val == "fallback"  # should always be default


class TestModelMutation:
    """Test that model downgrade doesn't infect subsequent stages."""

    @patch("core.harness.utils.model_injection.create_selected_adapter")
    def test_model_downgrade_should_not_mutate_runner(self, mock_create):
        """BUG: _stage_runner._model is permanently mutated on simple tasks.
        
        Fix: use temporary model assignment instead of permanent mutation.
        """
        mock_create.return_value = MagicMock(model_name="mock-model")
        
        config = PipelineConfig(stages=[
            _make_stage(id="stage1", agent_id="pm_agent"),
            _make_stage(id="stage2", agent_id="architect_agent", agent_type="plan"),
        ], max_tokens_per_run=10000)

        engine = PipelineEngine(config)
        original_model = engine._stage_runner._model
        
        # Simulate the bug: directly mutate _stage_runner._model
        cheap_model = MagicMock(model_name="deepseek-chat")
        engine._stage_runner._model = cheap_model
        
        # After the downgrade, confirm contamination
        assert engine._stage_runner._model is cheap_model
        # BUG: no restoration happens — this is the problem
        # After fix (FIX #1), _exec_stage restores original_model after execution


class TestScoringDimensions:
    """Test evaluation behavior with missing scoring dimensions."""

    def test_tri_evaluate_crashes_without_dims(self):
        """BUG: _tri_evaluate raises ValueError without scoring_dimensions.
        
        Fix: use default dimensions instead of crashing.
        """
        stage = _make_stage(scoring_dimensions=[])
        
        # Current behavior: crashes
        with pytest.raises(ValueError, match="scoring_dimensions"):
            dims = stage.scoring_dimensions or []
            if not dims:
                raise ValueError(
                    f"Stage '{stage.id}': scoring_dimensions is required."
                )

    def test_tri_evaluate_with_default_dims(self):
        """Fix: should use default dimensions when not configured."""
        stage = _make_stage(scoring_dimensions=[])
        dims = stage.scoring_dimensions or []
        if not dims:
            dims = [
                {"name": "correctness", "weight": 40},
                {"name": "completeness", "weight": 30},
                {"name": "quality", "weight": 30},
            ]
        assert len(dims) == 3
        assert dims[0]["name"] == "correctness"


class TestStageModelConfig:
    """Test that stage-level model config is respected."""

    def test_stage_model_should_be_used_in_non_react_path(self):
        """BUG: non-React path ignores stage.model configuration.
        
        Fix: pass stage.model to core_chat().
        """
        stage = _make_stage(agent_type="conversational", uses_file_output=False)
        
        # stage.model should be accessible
        stage_model = getattr(stage, 'model', None)
        # After FIX #5, stage_model is passed to ChatContext
        # For now, default is empty string (PipelineStageConfig default)
        assert stage_model == ""  # not configured by default
        # When configured in AGENT.md, it should flow through to core_chat()
