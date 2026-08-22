"""L2 import-existing-code tests (plan-app-factory-l2-import-repo.md §3.5/§3.8).

Covers core-side wiring without running a real pipeline:
1. _run_stage_skill's generic imported-context injection (behavior contract +
   intent anchors + referenced-file full text + listing) — driven by
   PipelineStageConfig.inject_imported_context.
2. skip_pytest_gate gate on test_execution_mode="pytest" stages.
"""
import asyncio
import json
import os

import pytest

from core.schemas_builder import PipelineStageConfig, PipelineConfig
from core.harness.execution.pipeline_engine import PipelineEngine


class _StubModel:
    """Minimal model stub — avoids ModelManager hardware detection in tests."""


def _make_engine() -> PipelineEngine:
    stage = PipelineStageConfig(
        id="s1", agent_id="programmer", skill_name="code_generation",
        output_artifact="code", uses_file_output=True,
        inject_imported_context=True,
    )
    cfg = PipelineConfig(stages=[stage], max_tokens_per_run=10000, max_retry_attempts=1)
    return PipelineEngine(config=cfg, model=_StubModel())


def _imported_payload(root: str) -> dict:
    return {
        "root": root,
        "manifest": [
            {"path": "src/auth/login.py", "size": 120, "lang": "py"},
            {"path": "src/models/user.py", "size": 201, "lang": "py"},
        ],
        "modify_files": [
            {"path": "src/auth/login.py", "intent": "登录增加验证码校验"},
        ],
        "behavior_prompt": "## 行为契约（重写而非合并）\n必须基于旧文件重写，保留对外接口。",
        "intent_anchor_block": (
            "## files to modify (user-confirmed paths + intents)\n"
            "- src/auth/login.py — 意图：登录增加验证码校验"),
    }


class TestImportedContextInjection:
    """_run_stage_skill appends imported context when inject_imported_context=true."""

    @pytest.mark.asyncio
    async def test_injected_context_contains_contract_intent_and_file(self, tmp_path, monkeypatch):
        src = tmp_path / "src/auth"
        src.mkdir(parents=True)
        (src / "login.py").write_text("def login():\n    return 'legacy'\n")
        (src / "user.py").write_text("class User: pass\n")

        captured = {}

        async def fake_llm(*args, **kwargs):
            msgs = kwargs.get("messages") or (args[1] if len(args) > 1 else None)
            # user message (index 1) carries the stage context incl. imported_repo injection
            captured["system"] = msgs[1].get("content", "") if isinstance(msgs, list) and len(msgs) > 1 else str(msgs)
            return type("R", (), {"content": "ok", "usage": {}})()

        monkeypatch.setattr(
            "core.harness.syscalls.llm.sys_llm_generate", fake_llm)
        monkeypatch.setattr(
            "core.harness.utils.model_injection.best_model_for_purpose",
            lambda purpose: "test-model")

        engine = _make_engine()
        state = {
            "session_id": "t1", "phase": "executing",
            "output_dir": str(tmp_path / "out"), "description": "需求",
            "imported_repo": _imported_payload(str(tmp_path)),
            "skip_pytest_gate": False,
        }
        await engine._run_stage_skill(engine._config.stages[0], state)

        ctx = captured.get("system") or ""
        # 行为契约（重写而非合并）
        assert "重写而非合并" in ctx
        # 意图锚点
        assert "登录增加验证码校验" in ctx
        assert "src/auth/login.py" in ctx
        # 被引用文件全文（重写依据）
        assert "def login():" in ctx and "return 'legacy'" in ctx
        # 未引用文件仅清单（不注入全文）
        assert "class User: pass" not in ctx
        assert "src/models/user.py" in ctx  # listing only

    @pytest.mark.asyncio
    async def test_no_injection_when_flag_off(self, tmp_path, monkeypatch):
        src = tmp_path / "src"
        src.mkdir()
        (src / "login.py").write_text("def login(): pass\n")
        captured = {}

        async def fake_llm(*args, **kwargs):
            msgs = kwargs.get("messages") or (args[1] if len(args) > 1 else None)
            # user message (index 1) carries the stage context incl. imported_repo injection
            captured["system"] = msgs[1].get("content", "") if isinstance(msgs, list) and len(msgs) > 1 else str(msgs)
            return type("R", (), {"content": "ok", "usage": {}})()

        monkeypatch.setattr(
            "core.harness.syscalls.llm.sys_llm_generate", fake_llm)
        monkeypatch.setattr(
            "core.harness.utils.model_injection.best_model_for_purpose",
            lambda purpose: "test-model")

        stage = PipelineStageConfig(
            id="s1", agent_id="programmer", skill_name="code_generation",
            output_artifact="code", uses_file_output=True,
            inject_imported_context=False,
        )
        cfg = PipelineConfig(stages=[stage], max_tokens_per_run=10000, max_retry_attempts=1)
        engine = PipelineEngine(config=cfg, model=_StubModel())
        state = {
            "session_id": "t2", "phase": "executing",
            "output_dir": str(tmp_path / "out"), "description": "需求",
            "imported_repo": _imported_payload(str(tmp_path)),
            "skip_pytest_gate": False,
        }
        await engine._run_stage_skill(stage, state)
        ctx = captured.get("system") or ""
        assert "imported existing code" not in ctx
        assert "def login():" not in ctx


class TestSkipPytestGate:
    """skip_pytest_gate=true → test-execution stage short-circuits with markers."""

    @pytest.mark.asyncio
    async def test_skip_gate_marks_state(self, tmp_path):
        stage = PipelineStageConfig(
            id="s1", agent_id="test_executor", skill_name="test_executor",
            output_artifact="test_report", test_result_key="test_report",
            test_execution_mode="pytest",
        )
        cfg = PipelineConfig(stages=[stage], max_tokens_per_run=10000, max_retry_attempts=1)
        engine = PipelineEngine(config=cfg, model=_StubModel())
        state = {
            "session_id": "t3", "phase": "executing",
            "output_dir": str(tmp_path / "out"), "description": "需求",
            "skip_pytest_gate": True,
        }
        result = await engine._run_stage_skill(stage, state)
        assert result["_skip_pytest_gate"] is True
        assert result["_test_pass_rate"] is None
        assert result["_has_tests"] is False
        assert result["_test_gate_skipped_reason"]
        report = result["test_report"]
        assert report["recommendation"] == "APPROVED_SKIPPED"
        assert report["error"] == "pytest_gate_skipped"

    @pytest.mark.asyncio
    async def test_no_skip_when_gate_false(self, tmp_path):
        stage = PipelineStageConfig(
            id="s1", agent_id="test_executor", skill_name="test_executor",
            output_artifact="test_report", test_result_key="test_report",
            test_execution_mode="pytest",
        )
        cfg = PipelineConfig(stages=[stage], max_tokens_per_run=10000, max_retry_attempts=1)
        engine = PipelineEngine(config=cfg, model=_StubModel())
        state = {
            "session_id": "t4", "phase": "executing",
            "output_dir": str(tmp_path / "out"), "description": "需求",
            "skip_pytest_gate": False,
        }
        result = await engine._run_stage_skill(stage, state)
        assert "_skip_pytest_gate" not in result
        assert "APPROVED_SKIPPED" not in str(result.get("test_report"))
