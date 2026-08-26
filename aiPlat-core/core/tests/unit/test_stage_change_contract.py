"""SBA 原则 12 测试（2026-08-26）：pipeline stage 产物 key 链（Change Contract）。

覆盖:
- input_artifacts 引用存在 → 通过（上游 output_artifact 提供）
- input_artifacts 引用缺失 → 报错（Change Contract 断裂）
- 内置输入（description 等）不误报
"""
from __future__ import annotations

from types import SimpleNamespace

CORE_ROOT = __import__("pathlib").Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(CORE_ROOT))

from core.api.core_facade import validate_pipeline_stages


def _stage(sid, output="", inputs=None):
    return SimpleNamespace(id=sid, agent_id="a1", required_skills=[],
                           failure_strategy="fail_pipeline",
                           output_artifact=output, input_artifacts=inputs or [])


class TestChangeContract:
    def test_chain_complete_passes(self):
        """上游 output → 下游 input 引用完整 → 通过。"""
        stages = [
            _stage("pm", output="prd"),
            _stage("arch", inputs=["prd", "description"]),
        ]
        d = validate_pipeline_stages(stages)
        assert d["valid"] is True, d

    def test_broken_reference_rejected(self):
        """下游引用不存在于上游 output_artifact → 报错（Change Contract 断裂）。"""
        stages = [
            _stage("pm", output="prd"),
            _stage("arch", inputs=["architecture"]),  # 无上游提供 architecture
        ]
        d = validate_pipeline_stages(stages)
        assert d["valid"] is False, d
        assert any("Change Contract" in e and "architecture" in e for e in d["errors"]), d

    def test_builtin_inputs_allowed(self):
        """内置输入（description/user_input/start.inputs）不误报。"""
        stages = [_stage("pm", inputs=["description", "user_input", "start.inputs"])]
        d = validate_pipeline_stages(stages)
        assert d["valid"] is True, d

    def test_multi_stage_chain(self):
        """多级链：prd → arch → code 引用各自上游。"""
        stages = [
            _stage("pm", output="prd"),
            _stage("arch", output="architecture", inputs=["prd"]),
            _stage("dev", output="code", inputs=["architecture"]),
        ]
        assert validate_pipeline_stages(stages)["valid"] is True
