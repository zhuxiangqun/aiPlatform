"""P0-A2 回归防护: pipeline 执行链路无未定义符号（NameError）测试。

背景: pipeline_execution.py 的 PipelineConfig/PipelineEngine 未 import（存量
NameError）导致应用工厂 rebuild 无输出——该链路必须有测试防护。
"""
import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "aiPlat-core"))


def _gather_imports(tree):
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imported.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                imported.add(a.asname or a.name)
    return imported


class TestPipelineExecutionNoUndefinedSymbols:
    """pipeline_execution.py 的函数内不得使用未 import 的大写符号。"""

    @pytest.fixture(scope="class")
    def module_tree(self):
        fp = ROOT / "aiPlat-core/core/api/routers/pipeline_execution.py"
        return ast.parse(fp.read_text(encoding="utf-8"))

    def test_pipeline_config_imported(self, module_tree):
        imported = _gather_imports(module_tree)
        assert "PipelineConfig" in imported, "PipelineConfig 未 import — rebuild NameError"
        assert "PipelineStageConfig" in imported, "PipelineStageConfig 未 import"

    def test_no_pipeline_engine_direct_construction(self, module_tree):
        src = ast.unparse(module_tree)
        assert "engine = PipelineEngine(" not in src, "存在 PipelineEngine 直构"

    def test_no_pipeline_engine_direct_import(self, module_tree):
        for node in ast.walk(module_tree):
            if isinstance(node, ast.ImportFrom) and node.module == "core.harness.execution.pipeline_engine":
                raise AssertionError("直导 pipeline_engine — 应经 CoreFacade")

    def test_execute_pipeline_symbols_resolvable(self, module_tree):
        src = ast.unparse(module_tree)
        for sym in ["PipelineConfig", "PipelineStageConfig", "create_pipeline_engine", "best_model_for_purpose"]:
            assert sym in src, f"{sym} 不可解析"
