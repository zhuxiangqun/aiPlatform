"""
P1 回归测试（core 侧）— 应用工厂审计 P1-6 / P1-7 修复验证（2026-08-25）。

覆盖:
- P1-6: _run_chained_skill 引用未定义变量 stage
  （pipeline_engine.py:4619 `getattr(stage, 'stage_timeout_seconds', 300)` —— 函数签名
  无 stage 参数 → NameError 被 except 吞 → 链式技能永不执行。修复：改用函数内已定义的
  `_chain_stage`）
- P1-7: skip_pytest_gate 双份并行实现
  （pipeline_engine.py:3958 `_run_stage_skill` 与 pipeline_eval.py:196 `_exec_test_runner`
  各自内联落盘 APPROVED_SKIPPED —— 双份漂移风险。修复：收敛到共享
  `_apply_skip_pytest_gate(state, result_key)`，两处调用）

运行方式（仓库根）：
    TMPDIR=$(pwd)/../.tmp_pytest AIPLAT_HOME=$(pwd)/../.tmp_pytest/home \
        python3 -m pytest aiPlat-core/core/tests/unit/test_pipeline_engine_p1b_fixes.py -v
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

CORE_ROOT = Path(__file__).resolve().parents[3]
ENGINE_PATH = CORE_ROOT / "core" / "harness" / "execution" / "pipeline_engine.py"
EVAL_PATH = CORE_ROOT / "core" / "harness" / "execution" / "pipeline_eval.py"

import sys
sys.path.insert(0, str(CORE_ROOT))

from core.harness.execution.pipeline_engine import PipelineEngine
from core.harness.execution.pipeline_eval import _apply_skip_pytest_gate


# ---- P1-6: _run_chained_skill 未定义 stage ----

class TestP1_6ChainedSkillUndefinedStage:
    def test_no_undefined_stage_reference(self):
        """静态证据：_run_chained_skill 体内不得再引用未定义变量 stage。"""
        src = ENGINE_PATH.read_text(encoding="utf-8")
        m = re.search(
            r"async def _run_chained_skill\(.*?(?=\n    @staticmethod|\n    def _write_artifact_file|\n    async def )",
            src, re.DOTALL,
        )
        assert m, "找不到 _run_chained_skill"
        body = m.group(0)
        # 函数签名没有 stage 参数
        assert "stage:" not in body.split(")", 1)[0], "函数签名不应有 stage 参数"
        # 不得再对未定义的 stage 做 getattr
        assert "getattr(stage," not in body, "P1-6 未修复：仍引用未定义变量 stage"
        # 应改用 _chain_stage
        assert "getattr(_chain_stage, 'stage_timeout_seconds'" in body, \
            "P1-6 未修复：未改用 _chain_stage 读超时"

    def test_chained_skill_executes_through_stage_runner(self):
        """行为证据：修复前 NameError 被吞（stage_runner 永不执行）；修复后正常执行。"""
        engine = PipelineEngine.__new__(PipelineEngine)
        mock_runner = SimpleNamespace(run=AsyncMock(return_value=(
            "```json\n{\"result\": \"ok\", \"detail\": \"chain executed\", "
            "\"evidence\": \"this is a sufficiently long structured output payload "
            "that exceeds the minimum length threshold for chain result storage\"}\n```"
        )))
        engine._stage_runner = mock_runner
        state = {
            "test_report": {"raw_output": "upstream content for chain execution"},
            "_generated_agent": "",
        }

        async def _run():
            return await engine._run_chained_skill(
                "test_executor", state, "test_report", "_chained_result")

        result = asyncio.run(_run())
        # stage_runner.run 被真正调用（修复前在 wait_for 参数求值即 NameError）
        mock_runner.run.assert_awaited_once()
        # 结果落盘到 result_artifact_key
        assert "_chained_result" in result
        assert "chain executed" in result["_chained_result"].get("raw_output", "")
        assert result["_progress"]["status"] == "completed"


# ---- P1-7: skip_pytest_gate 双份收敛 ----

class TestP1_7SkipPytestGateConverged:
    def test_shared_helper_marks_state(self):
        """行为证据：_apply_skip_pytest_gate 统一落盘 APPROVED_SKIPPED。"""
        state = {"skip_pytest_gate": True}
        assert _apply_skip_pytest_gate(state, "test_report") is True
        assert state["_test_pass_rate"] is None
        assert state["_has_tests"] is False
        assert state["_skip_pytest_gate"] is True
        assert "estimated" in state["_test_gate_skipped_reason"]
        report = state["test_report"]
        assert report["recommendation"] == "APPROVED_SKIPPED"
        assert report["error"] == "pytest_gate_skipped"
        assert report["pass_rate"] == 0

    def test_shared_helper_noop_without_flag(self):
        """未设置 skip_pytest_gate → 返回 False 且不污染 state。"""
        state = {"output_dir": "/tmp"}
        assert _apply_skip_pytest_gate(state, "test_report") is False
        assert "test_report" not in state
        assert "_test_gate_skipped_reason" not in state

    def test_both_callers_use_shared_helper(self):
        """静态证据：两处调用点都收敛到 _apply_skip_pytest_gate，不再内联落盘。"""
        eng_src = ENGINE_PATH.read_text(encoding="utf-8")
        eval_src = EVAL_PATH.read_text(encoding="utf-8")
        # pipeline_engine 导入共享函数
        assert "_apply_skip_pytest_gate" in eng_src
        # 两个文件中不再有内联的完整 APPROVED_SKIPPED 落盘（字典 + reason 一起出现）
        inline_pattern = r'["\']APPROVED_SKIPPED["\']\s*:.*?_test_gate_skipped_reason'
        assert not re.search(inline_pattern, eng_src), \
            "P1-7 未修复：pipeline_engine.py 仍内联落盘 APPROVED_SKIPPED"
        assert not re.search(inline_pattern, eval_src), \
            "P1-7 未修复：pipeline_eval.py 仍内联落盘 APPROVED_SKIPPED"
