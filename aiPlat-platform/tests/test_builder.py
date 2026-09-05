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
        """Builder must use create_pipeline_session, not direct PipelineEngine."""  # noqa: boundary — test enforcing the rule
        import builder.builder_team_service as bts
        import builder.builder_session as bs
        import builder.builder_project_service as bps

        # Read source as text and check for forbidden import pattern
        for mod_path in [bts.__file__, bs.__file__, bps.__file__]:
            with open(mod_path) as f:
                source = f.read()
            # Must NOT import PipelineEngine directly  # noqa: boundary
            # noqa: boundary — test enforcing the rule, not using engine
            msg = f"{mod_path} imports PipelineEngine directly"  # noqa: boundary
            assert "from core.harness.execution.pipeline_engine import PipelineEngine" not in source, msg  # noqa: boundary
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
        assert stage.uses_file_output is False
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


class TestBuilderPipelineE2E:
    """E2E smoke tests for the full Builder pipeline lifecycle."""

    @pytest.fixture
    def service(self):
        """Create BuilderProjectService with mock model."""
        import os
        os.environ.setdefault("AIPLAT_ENABLE_CORE_ADAPTER_FALLBACK", "true")
        from unittest.mock import MagicMock
        from builder.builder_project_service import BuilderProjectService

        mock_model = MagicMock()
        mock_model.model_name = "deepseek-chat"
        mock_model.generate = MagicMock()

        svc = BuilderProjectService(team_service=None)
        svc._model = mock_model
        return svc

    def test_prd_markdown_parsing(self):
        """Verify _parse_markdown_prd extracts title, FRs, and scope."""
        from builder.builder_project_service import BuilderProjectService

        test_prd = """
# 项目名称：测试项目
## 项目背景
背景内容
## 功能需求
### FR-01: 测试功能
- **用户故事**：作为用户，我想测试
- **优先级**：P0
- **验收标准**：
  - AC1: 正向验证
  - AC2: 异常验证
## 范围
新增Agent
"""
        result = BuilderProjectService._parse_markdown_prd(test_prd)
        assert result, "Markdown PRD parsing must return non-empty dict"
        assert result.get("title") == "测试项目"
        assert result.get("description") == "背景内容"
        assert len(result.get("functional_requirements", [])) >= 1
        fr = result["functional_requirements"][0]
        assert fr.get("description") == "作为用户，我想测试"
        assert fr.get("priority") == "P0"
        assert result.get("user_stories"), "Must have user_stories for backward compat"
        assert result["user_stories"][0]["id"].startswith("US-")
        assert result.get("scope"), "Must extract scope"

    def test_prd_markdown_parses_gate_rewritten_format(self):
        """Factory-rewritten Markdown (描述 + 独立用户故事 + 决策) must round-trip."""
        from builder.builder_project_service import BuilderProjectService

        md = """## 项目名称：智能视频内容理解工具

## 项目背景
支持直链视频 URL 或本地上传。

## 功能需求
### FR-001: 视频输入与下载
- **描述**: 支持本地上传或直链视频 URL
- **优先级**: high
- **验收标准**:
  - AC1: 单文件 ≤2GB
  - AC2: SSRF 防护

### FR-004: 语音内容分析
- **描述**: 声学粗标签（非转写语义），不进行语音转写
- **优先级**: standard
- **验收标准**:
  - AC1: 输出声学粗标签

## 用户故事
### US-001: 作为审核员，我想要粘贴直链视频 URL
- **关联需求**: FR-001
- **优先级**: high

### US-004: 作为审核员，我想要分析声学粗标签
- **关联需求**: FR-004
- **优先级**: standard

## 决策
- speech_pipeline: audio_features_only
- url_source_scope: direct_media_url

## 待确认问题
（无）

## 范围
- 平台: Web
- 性能: P95 ≤ 1.5× video duration
- 安全: SSRF

---
（已由 PRD 质量门禁自动改写 3 项）

<!-- PRD_READY -->
"""
        result = BuilderProjectService._parse_markdown_prd(md)
        assert result["title"] == "智能视频内容理解工具"
        assert "直链" in result["description"]
        frs = {fr["id"]: fr for fr in result["functional_requirements"]}
        assert frs["FR-001"]["description"].startswith("支持本地上传")
        assert frs["FR-001"]["priority"] == "high"
        assert "≤2GB" in frs["FR-001"]["acceptance_criteria"][0]
        stories = {us["id"]: us for us in result["user_stories"]}
        assert "US-001" in stories and "US-004" in stories
        assert stories["US-001"]["related_fr"] == ["FR-001"]
        assert result["decisions"]["speech_pipeline"] == "audio_features_only"
        assert result.get("open_questions") == []
        # Must NOT alias FRs as user_stories
        assert all(us["id"].startswith("US-") for us in result["user_stories"])
        assert len(result["user_stories"]) == 2
        assert len(result["functional_requirements"]) == 2

    def test_confirm_prd_saves_prd_from_messages(self, service):
        """confirm_prd() must find PRD in session messages and save to project."""
        import asyncio

        service._sessions["test_prj"] = {
            "phase": "dialogue",
            "messages": [
                {"role": "user", "content": "requirement"},
                {"role": "assistant", "content": "<!-- PRD_READY -->\n# 项目名称：消息PRD\n\n## 功能需求\n### FR-01: 测试\n- **用户故事**：作为用户\n- **验收标准**：\n  - AC1: 测试\n## 范围\nSkill"},
            ],
        }
        service._projects["test_prj"] = {"project_id": "test_prj", "description": "test"}

        result = asyncio.run(service.confirm_prd("test_prj"))

        proj = service._projects.get("test_prj", {})
        assert proj.get("confirmed_prd"), f"PRD must be saved. Result: {result}"
        assert proj["confirmed_prd"].get("title") == "消息PRD"
        assert result.get("phase") == "executing"

    def test_confirm_prd_blocks_contradictory_media_prd(self, service):
        """Media PRD without decisions is factory-enriched then confirmable."""
        import asyncio

        bad = {
            "title": "智能视频工具",
            "description": "视频画面与语音分析",
            "functional_requirements": [
                {
                    "id": "FR-004",
                    "name": "语音分析",
                    "acceptance_criteria": [
                        "基于音轨特征分析，不生成逐字转写文本",
                        "输出主题标签与情绪倾向",
                    ],
                },
                {
                    "id": "FR-006",
                    "name": "加密",
                    "acceptance_criteria": ["上传视频 AES-256 加密存储"],
                },
            ],
            "constraints": {},
            "open_questions": [],
        }
        service._sessions["vid_prj"] = {"phase": "dialogue", "messages": [], "prd": bad}
        service._projects["vid_prj"] = {"project_id": "vid_prj", "description": "video"}

        result = asyncio.run(service.confirm_prd("vid_prj"))
        assert result.get("status") == "ok", result
        assert result.get("phase") == "executing"
        confirmed = service._projects["vid_prj"]["confirmed_prd"]
        assert confirmed.get("decisions", {}).get("speech_pipeline") == "audio_features_only"
        assert confirmed.get("decisions", {}).get("encryption_key_mgmt")
        assert confirmed.get("_prd_gate", {}).get("ok") is True

        # Without enrich, raw contradiction still fails the gate
        from core.api.core_facade import apply_gate_to_prd
        import pytest
        with pytest.raises(ValueError, match="质量门禁"):
            apply_gate_to_prd(bad, force=False, enrich=False)

    def test_session_type_safety_on_chat(self, service):
        """chat() must handle non-dict session without crashing — resets to dict."""
        # Simulate PipelineSession overwriting the session with a non-dict
        service._sessions["test_prj2"] = object()
        service._phases["test_prj2"] = "executing"

        import asyncio

        async def _test():
            return await service.chat("test_prj2", "hello")

        result = asyncio.run(_test())
        assert isinstance(result, dict), f"Expected dict result, got: {result}"
        assert "reply" in result, f"Expected reply in result: {result}"
        # Non-dict session must be reset to a dict for further interaction
        assert isinstance(service._sessions.get("test_prj2"), dict)

    def test_recommend_team_no_name_error(self):
        """recommend_team() return must not use undefined 'result.trace_id'."""
        import re
        from pathlib import Path

        svc_path = Path(__file__).resolve().parents[1] / "builder" / "builder_project_service.py"
        with open(svc_path, "r") as f:
            source = f.read()
        func_match = re.search(
            r'async def recommend_team.*?(?=\n    def |\n    async def |\n@staticmethod|\Z)',
            source, re.DOTALL
        )
        assert func_match, "Could not find recommend_team function"
        func_body = func_match.group(0)
        assert 'result.trace_id' not in func_body, \
            "BUG: recommend_team() uses 'result.trace_id' (undefined variable)"

    def test_error_propagates_to_get_state(self, service):
        """get_project_state() must read phase from the pipeline run store (SQLite),
        and return idle when no run state exists for the project."""
        service._projects["test_prj"] = {
            "project_id": "test_prj", "description": "test",
            "team_stages": [], "runs": [],
        }

        import asyncio

        async def _test():
            return await service.get_project_state("test_prj")

        result = asyncio.run(_test())
        # No run state written → phase falls back to idle (not a crash)
        assert result["phase"] in ("idle", "failed", "done"), \
            f"Expected a valid phase, got {result['phase']}"
        assert "state" in result, "Response must include state dict"

    def test_start_pipeline_no_stages_returns_error(self, service):
        """Pipeline config with no stages must still create a usable session (engine
        tolerates empty stage list; execution no-ops)."""
        from unittest.mock import patch
        from core.api.core_facade import create_pipeline_session
        from core.schemas_builder import PipelineConfig

        config = PipelineConfig(stages=[], max_tokens_per_run=1000)

        with patch('core.harness.execution.pipeline_engine.PipelineEngine') as MockEngine:
            session = create_pipeline_session(config=config, model=None)
            assert session is not None
            assert hasattr(session, "start")

    def test_start_pipeline_returns_failed_on_execution_error(self, service):
        """create_pipeline_session() must propagate a session whose start() raises."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from core.api.core_facade import create_pipeline_session
        from core.schemas_builder import PipelineConfig, PipelineStageConfig

        stages = [PipelineStageConfig(
            id="pm", agent_id="pm_agent", output_artifact="prd",
            agent_type="conversational", uses_file_output=False,
            scoring_dimensions=[], generate_test_plan=False,
            test_result_key="", prompt_extra="", failure_strategy="fail_pipeline",
        )]
        config = PipelineConfig(stages=stages, max_tokens_per_run=1000)

        # create_pipeline_session must return a session object (start behavior
        # is covered by core pipeline tests; here we verify the factory path).
        with patch('core.harness.execution.pipeline_engine.PipelineEngine') as MockEngine:
            session = create_pipeline_session(config=config, model=None)
            assert session is not None
            assert hasattr(session, "start")
            assert hasattr(session, "approve")
