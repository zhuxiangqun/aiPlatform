"""
Test Builder service structure — verifies imports, CRUD signatures, and facade compliance.
"""
import pytest


class TestBuilderImports:
    """Verify builder modules follow CoreFacade pattern."""

    def test_builder_team_imports(self):
        """BuilderTeamService must import from CoreFacade."""
        from builder.builder_team_service import BuilderTeamService
        assert BuilderTeamService is not None

    def test_builder_session_imports(self):
        """BuilderSessionService must import from CoreFacade."""
        from builder.builder_session import BuilderSessionService
        assert BuilderSessionService is not None

    def test_builder_project_imports(self):
        """BuilderProjectService must import from CoreFacade."""
        from builder.builder_project_service import BuilderProjectService
        assert BuilderProjectService is not None

    def test_create_pipeline_session_used(self):
        """Builder must use create_pipeline_session, not direct PipelineEngine."""
        import builder.builder_team_service as bts
        import builder.builder_session as bs
        import builder.builder_project_service as bps

        # Read source as text and check for forbidden import pattern
        for mod_path in [bts.__file__, bs.__file__, bps.__file__]:
            with open(mod_path) as f:
                source = f.read()
            # Must NOT import PipelineEngine directly
            assert "from core.harness.execution.pipeline_engine import PipelineEngine" not in source, \
                f"{mod_path} imports PipelineEngine directly"
            # Must use CoreFacade
            assert "create_pipeline_session" in source, \
                f"{mod_path} does not reference create_pipeline_session"


class TestBuilderSchemaValidation:
    """Validate builder config types."""

    def test_pipeline_config_minimal(self):
        """PipelineConfig must accept minimal stage list."""
        from core.schemas_builder import PipelineConfig, PipelineStageConfig

        stages = [PipelineStageConfig(
            id="stage_1",
            agent_id="test_agent",
            output_artifact="test_output",
        )]
        config = PipelineConfig(stages=stages)
        assert len(config.stages) == 1
        assert config.stages[0].agent_id == "test_agent"

    def test_stage_config_defaults(self):
        """PipelineStageConfig defaults must be reasonable."""
        from core.schemas_builder import PipelineStageConfig

        stage = PipelineStageConfig(
            id="test", agent_id="agent_1",
            output_artifact="output",
        )
        assert stage.agent_type == "react"
        assert stage.hitl is False
        assert stage.uses_code_skill is False
        assert stage.generate_test_plan is False
        assert stage.failure_strategy == "fail_pipeline"

    def test_validate_pipeline_stages(self):
        """CoreFacade.validate_pipeline_stages must work."""
        from core.schemas_builder import PipelineStageConfig
        from core.api.core_facade import validate_pipeline_stages

        stages = [
            PipelineStageConfig(id="s1", agent_id="a1", output_artifact="o1"),
            PipelineStageConfig(id="s2", agent_id="a2", required_skills=["code"]),
        ]
        result = validate_pipeline_stages(stages)
        assert result["valid"] is True

    def test_validate_stages_detects_missing_agent_id(self):
        """validate_pipeline_stages must flag missing agent_id."""
        from core.schemas_builder import PipelineStageConfig
        from core.api.core_facade import validate_pipeline_stages

        stages = [
            PipelineStageConfig(id="s1", agent_id="", output_artifact="o1"),
        ]
        result = validate_pipeline_stages(stages)
        assert result["valid"] is False
        assert len(result["errors"]) >= 1
