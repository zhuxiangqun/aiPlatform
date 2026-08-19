"""
Test PipelineSession facade — verifies platform uses CoreFacade correctly.
"""
import pytest


class TestPipelineSession:
    """PipelineSession is the sole interface for pipeline execution."""

    def test_import_uses_core_facade(self):
        """Platform must import PipelineSession through CoreFacade."""
        from core.api.core_facade import PipelineSession, create_pipeline_session
        assert PipelineSession is not None
        assert create_pipeline_session is not None

    def test_core_facade_exports(self):
        """CoreFacade must export all required methods."""
        import core.api.core_facade as cf
        required = [
            "PipelineSession", "create_pipeline_session",
            "validate_pipeline_stages", "apply_agent_md_to_stage",
            "create_agent", "get_default_model",
            "core_chat", "ChatContext", "ChatResult",
            "extract_json",
            "seed_all_registries", "get_skill_registry",
            "get_tool_registry", "get_agent_registry",  # P0-B4: 统一入口（facade 冗余已删）
            "record_changeset", "new_change_id",
            "create_chat_service", "create_conversation_service",
        ]
        for name in required:
            assert hasattr(cf, name), f"CoreFacade missing: {name}"

    def test_create_pipeline_session_accepts_minimal_args(self):
        """create_pipeline_session() must work with minimal args."""
        from core.schemas_builder import PipelineConfig, PipelineStageConfig
        from core.api.core_facade import create_pipeline_session

        stages = [PipelineStageConfig(
            id="test", agent_id="test_agent",
            output_artifact="test_output",
        )]
        config = PipelineConfig(stages=stages, max_tokens_per_run=1000)

        try:
            session = create_pipeline_session(config=config)
            assert session is not None
            assert hasattr(session, "start")
            assert hasattr(session, "approve")
            assert hasattr(session, "reject")
            assert hasattr(session, "rollback")
            assert hasattr(session, "snapshot")
        except Exception as e:
            # May fail if no LLM model configured — that's OK in unit tests
            if "model" in str(e).lower() or "adapter" in str(e).lower():
                pytest.skip(f"Model not configured: {e}")
            raise
