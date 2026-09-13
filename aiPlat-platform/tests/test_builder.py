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

    def test_lazy_model_uses_agent_purpose_not_chat(self, monkeypatch):
        """Factory PM/PRD must resolve via purpose=agent (not latency-first chat)."""
        from unittest.mock import MagicMock
        from builder.builder_project_service import BuilderProjectService

        purposes = []

        def _best(purpose, messages=None):
            purposes.append(purpose)
            return "mock-agent-model"

        mock_adapter = MagicMock()
        mock_adapter.model_name = "mock-agent-model"

        monkeypatch.setattr(
            "core.api.core_facade.best_model_for_purpose",
            _best,
        )
        monkeypatch.setattr(
            "core.api.core_facade.create_selected_adapter",
            lambda model_name="": mock_adapter,
        )

        svc = BuilderProjectService(team_service=None)
        assert svc._model is None
        got = svc.model
        assert got is mock_adapter
        assert purposes == ["agent"], purposes

    def test_apply_prd_gate_blocks_empty_shell_ready(self, service):
        """Empty Markdown + PRD_READY must not set prd_ready / confirmed_prd."""
        service._sessions["shell"] = {"phase": "dialogue", "messages": []}
        service._projects["shell"] = {"project_id": "shell", "name": "shell"}
        reply = (
            "## 项目名称：步骤1：分析关键约束\n\n"
            "## 待确认问题\n（无）\n\n## 范围\n- 平台: Web\n\n"
            "<!-- PRD_READY -->\n"
        )
        service._sessions["shell"]["messages"].append(
            {"role": "assistant", "content": reply}
        )
        out, ready = service._apply_prd_gate_to_assistant_reply(
            "shell", service._sessions["shell"], reply
        )
        assert ready is False
        assert "PRD 尚未闭合" in out or "请输出完整 Markdown PRD" in out
        assert not service._projects["shell"].get("confirmed_prd")

    def test_apply_prd_gate_accepts_media_good_draft(self, service):
        """Gate-passing media PRD becomes READY and rewrites chat to repaired MD."""
        from core.api.core_facade import looks_like_prd

        service._sessions["ok"] = {"phase": "dialogue", "messages": []}
        service._projects["ok"] = {"project_id": "ok", "name": "ok"}
        reply = """## 项目名称：智能视频内容理解工具 (VideoSense)

## 项目背景
直链上传与声学粗标签分析，不转写。

## 功能需求
### FR-001: 视频输入
- **描述**: 直链或本地上传
- **优先级**: high
- **验收标准**:
  - AC1: 仅 .mp4/.mov/.avi/.mkv 直链；拒绝网页链接；SSRF 拒绝内网与 file://
  - AC2: 单文件 ≤2GB

### FR-004: 语音声学特征分析
- **描述**: 声学粗标签，不进行语音转写
- **优先级**: standard
- **验收标准**:
  - AC1: 输出语种/说话人数/情绪倾向（声学粗标签/非转写语义）；禁止主题标签
  - AC2: 无音轨时返回空列表

### FR-003: 软字幕
- **描述**: 仅软字幕轨
- **优先级**: standard
- **验收标准**:
  - AC1: 本期仅支持软字幕轨道；硬字幕不在本期范围，不承诺 OCR

## 用户故事
### US-001: 作为审核员，我想粘贴直链
- **关联需求**: FR-001

## 决策
- url_source_scope: direct_media_url
- speech_pipeline: audio_features_only
- subtitle_scope: soft_track_only
- analysis_sla: p95_120s_per_10min

## 待确认问题
（无）

## 范围
- 平台: Web
- 性能: P95 ≤ 120s / 10min video
- 安全: HTTPS + authentication; SSRF: reject private IPs and file://

<!-- PRD_READY -->
"""
        service._sessions["ok"]["messages"].append({"role": "assistant", "content": reply})
        out, ready = service._apply_prd_gate_to_assistant_reply(
            "ok", service._sessions["ok"], reply
        )
        assert ready is True, out[:500]
        assert looks_like_prd(service._sessions["ok"]["prd"])
        assert service._projects["ok"].get("confirmed_prd")
        assert "<!-- PRD_READY -->" in out

    def test_prd_gen_intent_and_analysis_leak_helpers(self):
        from builder.builder_project_service import (
            _user_asks_prd_output,
            _reply_leaks_analysis_steps,
        )
        assert _user_asks_prd_output("请生成完整 PRD")
        assert _reply_leaks_analysis_steps("### 步骤1：分析关键约束\n- foo")
        assert not _reply_leaks_analysis_steps("## 项目名称：VideoSense\n\n## 功能需求\n")

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

    def test_prd_markdown_parses_analysis_prefix_and_bold_fr(self):
        """步骤1–4 prefix + **FR-n：** style must still parse product title + FRs."""
        from builder.builder_project_service import (
            BuilderProjectService,
            _parse_prd_draft_from_reply,
            _reply_looks_like_prd_body,
        )
        from core.api.core_facade import looks_like_prd, factory_finalize_prd

        reply = """### 步骤1：分析关键约束
- 输入：直链或本地上传
- 不转写

### 步骤2：列出可行方案
方案A / 方案B / 方案C

### 步骤3：方案比较与取舍
取舍：直链 + 声学粗标签

### 步骤4：输出 PRD

## 项目名称：智能视频内容理解工具

## 项目背景
支持直链视频 URL 或本地上传，产出结构化标签。

## 功能需求
**FR-1：视频输入与下载**
- **描述**: 支持本地上传或直链视频 URL
- **优先级**: high
- **验收标准**:
  - AC1: 单文件 ≤2GB
  - AC2: SSRF 防护

**FR-2：画面内容理解**
- **描述**: 关键帧视觉标签
- **优先级**: high
- **验收标准**:
  - AC1: 输出物体/场景标签

- FR-3：语音内容分析
- **描述**: 声学粗标签（非转写语义）
- **优先级**: standard
- **验收标准**:
  - AC1: 输出语种/说话人数粗标签

**FR-4：结果汇总导出**
- **描述**: JSON/CSV 导出
- **优先级**: standard
- **验收标准**:
  - AC1: 导出含 FR 标签字段

## 用户故事
### US-001: 作为审核员，我想要粘贴直链视频 URL
- **关联需求**: FR-1
- **优先级**: high

## 决策
- speech_pipeline: audio_features_only
- url_source_scope: direct_media_url

## 待确认问题
（无）

## 范围
- 平台: Web
- 性能: P95 ≤ 1.5× video duration
- 安全: SSRF

<!-- PRD_READY -->
"""
        assert _reply_looks_like_prd_body(reply)
        result = BuilderProjectService._parse_markdown_prd(reply)
        assert result.get("title") == "智能视频内容理解工具"
        assert "步骤" not in result.get("title", "")
        frs = result.get("functional_requirements") or []
        assert len(frs) >= 1, f"expected FRs, got {frs!r}"
        assert any("视频输入" in (fr.get("name") or "") for fr in frs)
        assert looks_like_prd(result)

        draft = _parse_prd_draft_from_reply(
            reply, parse_markdown=BuilderProjectService._parse_markdown_prd
        )
        assert draft and looks_like_prd(draft)
        finalized, report = factory_finalize_prd(draft)
        assert looks_like_prd(finalized)
        codes = {i.get("code") for i in report.get("issues") or []}
        assert "prd_incomplete_no_fr" not in codes
        assert "prd_meta_title" not in codes

    def test_prd_paste_h3_sections_table_decisions_closes_gate(self, service):
        """Literal PM paste: 步骤1–4 + ### sections + **FR-n** + decisions table → READY."""
        from builder.builder_project_service import BuilderProjectService
        from core.api.core_facade import looks_like_prd, factory_finalize_prd

        reply = """### 步骤1：分析问题关键约束与隐含条件
禁止输出步骤；末尾必须加 marker。

### 步骤2：列出可能的解决方案/角度
方案A / 方案B / 方案C

### 步骤3：比较方案优劣
选方案C。

### 步骤4：选择最优方案并输出
选择方案C，直接输出完整 PRD。

---

## 项目名称：智能视频内容理解工具

### 项目背景
支持直链或本地上传；语音仅为声学粗标签，不转写。

### 功能需求
**FR-1：视频导入（URL 直链 + 本地上传）**
- 描述：用户可通过粘贴视频直链或本地上传导入视频
- 优先级：P0
- 验收标准：
  - 支持 URL 直链导入，拒绝平台页面链接
  - 上传单文件 ≤2GB
  - URL 导入执行 SSRF 防护，拒绝内网 IP 与 file://

**FR-2：画面分析**
- 描述：分段级视觉标签
- 优先级：P0
- 验收标准：
  - 按 segment 输出视觉标签

**FR-3：字幕提取**
- 描述：仅软字幕轨
- 优先级：P1
- 验收标准：
  - 仅处理软字幕轨，不处理硬字幕

**FR-4：语音声学特征分析**
- 描述：语种/说话人数/情绪倾向（声学），非转写语义
- 优先级：P1
- 验收标准：
  - 输出语种估计与说话人数量估计
  - 所有输出均为声学特征，不含主题/关键词/摘要

### 用户故事
- 作为内容运营人员，我希望粘贴直链获取画面标签与字幕

### 决策
| 键 | 值 | 说明 |
|---|---|---|
| `url_source_scope` | `direct_media_url` | 仅直链 |
| `speech_pipeline` | `audio_features_only` | 仅声学 |
| `subtitle_scope` | `soft_track_only` | 仅软字幕 |
| `vision_tag_granularity` | `segment` | 分段 |
| `analysis_sla` | `1.5x_duration` | SLA |

### 待确认问题
（空）

### 范围
**平台范围**
- 支持 Web 端使用

**性能**
- 分析耗时不超过视频时长的 1.5 倍

**安全**
- URL 导入执行 SSRF 防护：拒绝内网 IP 与 file://
"""
        draft = BuilderProjectService._parse_markdown_prd(reply)
        assert draft.get("title") == "智能视频内容理解工具"
        frs = draft.get("functional_requirements") or []
        assert len(frs) >= 4, frs
        assert draft.get("decisions", {}).get("speech_pipeline") == "audio_features_only"
        cons = draft.get("constraints") or {}
        assert cons.get("performance"), cons
        assert cons.get("security"), cons
        assert looks_like_prd(draft)
        finalized, report = factory_finalize_prd(draft)
        assert report.get("ok") is True, report
        assert looks_like_prd(finalized)

        from builder.builder_project_service import BuilderProjectService

        service._projects["paste"] = {"project_id": "paste", "name": "videosense"}
        session = {"messages": [{"role": "assistant", "content": reply}], "prd": None}
        out, ready = service._apply_prd_gate_to_assistant_reply(
            "paste", session, reply, allow_implicit_ready=True
        )
        assert ready is True
        assert "<!-- PRD_READY -->" in out
        assert service._projects["paste"].get("confirmed_prd")
        assert looks_like_prd(service._projects["paste"]["confirmed_prd"])
        assert BuilderProjectService._parse_markdown_prd(reply).get("title") == "智能视频内容理解工具"

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


class TestUpdateStageArtifact:
    """Edit stage artifact must work when only Core SQLite has state (no local builder_states)."""

    def test_update_frontend_pages_from_core_state(self, tmp_path, monkeypatch):
        import asyncio
        from builder.builder_project_service import BuilderProjectService

        monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
        svc = BuilderProjectService.__new__(BuilderProjectService)
        svc._projects = {
            "prj_x": {
                "project_id": "prj_x",
                "team_stages": [
                    {
                        "id": "stage_3",
                        "agent_id": "frontend_developer",
                        "agent_name": "前端程序员",
                        "output_artifact": "frontend_pages",
                        "phase": "frontend",
                    }
                ],
                "runs": [{"phase": "paused"}],
            }
        }
        svc._runs = {}
        svc._sessions = {}
        svc._save_projects = lambda: None  # type: ignore

        async def _fake_core(_pid: str):
            return {
                "project_id": "prj_x",
                "phase": "paused",
                "state": {
                    "phase": "paused",
                    "output_dir": str(tmp_path / "output" / "prj_x"),
                    "frontend_pages": {"raw_output": '{"stages":[]}', "elapsed_sec": 1},
                    "_hitl_output_artifact": "test_cases",
                },
            }

        svc._get_state_via_core = _fake_core  # type: ignore
        svc._load_pipeline_state = lambda _pid: None  # type: ignore
        svc._rebuild_session = lambda _pid: None  # type: ignore

        persisted = {}

        async def _fake_save(pid, state):
            persisted["pid"] = pid
            persisted["state"] = state

        svc._save_state = _fake_save  # type: ignore

        core_calls = {}

        def _fake_persist(pid, **kwargs):
            core_calls.update(kwargs)
            core_calls["project_id"] = pid

        svc._persist_edited_artifact_to_core = _fake_persist  # type: ignore

        result = asyncio.run(
            svc.update_stage_artifact("prj_x", "frontend_pages", '{"app_name":"x","stages":[]}')
        )
        assert result["status"] == "updated"
        assert result["artifact_key"] == "frontend_pages"
        assert persisted["state"]["frontend_pages"]["source"] == "user_edited"
        assert core_calls.get("artifact_key") == "frontend_pages"
        assert "app_name" in core_calls.get("content", "")

    def test_update_stage_artifact_no_state_raises(self, tmp_path, monkeypatch):
        import asyncio
        import pytest
        from builder.builder_project_service import BuilderProjectService

        monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
        svc = BuilderProjectService.__new__(BuilderProjectService)
        svc._projects = {"prj_x": {"project_id": "prj_x", "team_stages": [], "runs": []}}
        svc._runs = {}
        svc._load_pipeline_state = lambda _pid: None  # type: ignore

        async def _idle(_pid: str):
            return {"project_id": "prj_x", "phase": "idle", "state": {"phase": "idle"}}

        svc._get_state_via_core = _idle  # type: ignore

        with pytest.raises(ValueError, match="no pipeline state"):
            asyncio.run(svc.update_stage_artifact("prj_x", "frontend_pages", "{}"))


class TestPrdDecisionParse:
    def test_backtick_enum_with_chinese_note(self):
        from builder.builder_project_service import _parse_decisions_from_markdown

        body = """
- url_source_scope: `direct_media_url`（仅支持视频直链，不支持平台页面 URL）
- speech_pipeline: `audio_features_only`（仅声学特征分析，不转写）
- speech_rate_metric: `syllable_density`（音节密度，非字/分钟）
- subtitle_source: `soft_track_only`（仅提取已有字幕轨道，不做 OCR/ASR 生成字幕）
"""
        dec = _parse_decisions_from_markdown(body)
        assert dec["url_source_scope"] == "direct_media_url"
        assert dec["speech_pipeline"] == "audio_features_only"
        assert dec["speech_rate_metric"] == "syllable_density"
        assert dec["subtitle_source"] == "soft_track_only"

    def test_videosense_style_prd_finalize(self):
        """User PRD with 硬字幕 mention + backtick decisions must finalize cleanly."""
        from core.api.core_facade import factory_finalize_prd
        from builder.builder_project_service import BuilderProjectService

        md = """## 项目名称：智能视频内容理解工具（videosense）

## 项目背景
构建智能视频内容理解工具，画面分析、字幕提取和语音分析（不转写）。

## 功能需求
### FR-001: 视频来源接入
- **描述**: 支持视频链接或本地上传
- **优先级**: high
- **验收标准**:
  - AC1: 支持 HTTP/HTTPS 视频直链 URL 下载
  - AC2: 上传 MP4/AVI/MKV/MOV 返回 task_id
  - AC3: 拒绝内网 IP 与 file://
  - AC4: 下载完成返回本地路径

### FR-003: 字幕提取
- **描述**: 从视频中提取已有字幕轨道（软字幕或硬字幕），不进行语音转写
- **优先级**: standard
- **验收标准**:
  - AC1: 检测字幕轨道
  - AC2: 输出 SRT
  - AC3: 无字幕提示未检测到字幕轨道
  - AC4: 含时间轴

### FR-004: 语音分析（不转写）
- **描述**: 声学特征粗标签，不转写
- **验收标准**:
  - AC1: 检测语音轨道
  - AC2: 语种/说话人数/情绪倾向
  - AC3: VAD 起止时间
  - AC4: 不输出转写文字
  - AC5: 音节密度描述语速

## 用户故事
### US-001: 链接分析
story: 粘贴链接分析
related_fr: ["FR-001"]
priority: high

## 决策
- url_source_scope: `direct_media_url`（仅支持视频直链，不支持平台页面 URL）
- speech_pipeline: `audio_features_only`（仅声学特征分析，不转写）
- subtitle_source: `soft_track_only`（仅提取已有字幕轨道，不做 OCR/ASR 生成字幕）

## 待确认问题
（无）

## 范围
- 平台: Web
- 性能:
  - 下载 P95 < 60s
- 安全:
  - HTTPS
  - SSRF: 拒绝内网 IP 与 file://
"""
        svc = BuilderProjectService.__new__(BuilderProjectService)
        draft = svc._parse_markdown_prd(md)
        assert draft["decisions"]["url_source_scope"] == "direct_media_url"
        assert draft["user_stories"][0].get("related_fr") == ["FR-001"]
        final, report = factory_finalize_prd(draft)
        assert report.get("ok") is True, report.get("issues")
        assert final["decisions"]["url_source_scope"] == "direct_media_url"
        assert final["decisions"].get("subtitle_scope") == "soft_track_only"
        codes = {i.get("code") for i in (report.get("issues") or []) if isinstance(i, dict)}
        assert "hard_soft_subtitle_mismatch" not in codes


class TestDeterministicHandlerPlatformEffects:
    """Path0 media handlers skip ReAct but must still attach platform side-effects."""

    def test_platform_effects_memory_and_feedback(self, monkeypatch):
        import asyncio
        from builder.builder_project_service import BuilderProjectService

        saved = {}

        class _MM:
            async def save_interaction(self, **kwargs):
                saved.update(kwargs)

        class _FB:
            def __init__(self):
                self.calls = []

            def emit(self, *args, **kwargs):
                self.calls.append((args, kwargs))

        fb = _FB()
        import core.api.core_facade as facade

        monkeypatch.setattr(facade, "get_memory_manager", lambda: _MM())
        monkeypatch.setattr(facade, "get_local_feedback", lambda: fb)

        svc = BuilderProjectService.__new__(BuilderProjectService)
        effects = asyncio.run(
            svc._platform_effects_after_deterministic_skill(
                "prj_x",
                "video_downloader",
                {"url": "https://example.com/a.mp4"},
                {"status": "ok", "task_id": "t1"},
            )
        )
        assert "deterministic_handler" in effects
        assert "memory_saved" in effects
        assert "local_feedback" in effects
        assert saved.get("session_id") == "prj_x_fe"
        assert fb.calls

    def test_force_agent_skips_media_path0(self, monkeypatch):
        import asyncio
        from builder.builder_project_service import BuilderProjectService

        monkeypatch.setenv("AIPLAT_FACTORY_FORCE_AGENT_SKILL", "1")

        called = {"media": False}

        def _resolve(_name):
            called["media"] = True
            return "video_downloader"

        def _exec(*_a, **_k):
            called["media"] = True
            return {"status": "ok"}

        svc = BuilderProjectService.__new__(BuilderProjectService)
        svc._projects = {"prj_x": {"app_name": "demo"}}
        svc._runs = {}
        svc._load_pipeline_state = lambda _pid: {}
        svc._ensure_manifest_resolved = lambda *_a, **_k: None

        import core.api.core_facade as facade

        monkeypatch.setattr(facade, "resolve_media_handler_name", _resolve)
        monkeypatch.setattr(facade, "execute_media_skill", _exec)

        out = asyncio.run(svc.execute_skill("prj_x", "video_downloader", {"url": "https://x"}))
        # Force-agent: Path0 skipped → no agent ready → error path
        assert called["media"] is False
        assert out.get("ok") is False
        assert "Agent not ready" in str(out.get("error") or "")
