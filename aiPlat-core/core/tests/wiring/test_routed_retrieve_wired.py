"""
Wiring assertion tests for RoutedRetrieveTool + sys_routed_retrieve.

CLAUDE.md §5.30 rule 10 (强制): 每个新建公共模块必须附带接线断言测试。

验证:
  - RoutedRetrieveTool 在 server.py 工具注册表有生产调用者（注册为 Agent 可调用工具）
  - sys_routed_retrieve 被 RoutedRetrieveTool 调用（生产链路：Tool → syscall）
  - _route_intent 是意图判定核心，被 sys_routed_retrieve 使用
"""
import pytest

from .conftest import has_production_caller


class TestRoutedRetrieveWired:

    def test_routed_retrieve_tool_registered_in_server(self):
        """RoutedRetrieveTool 必须注册进 server.py 工具注册表（Agent 可经 sys_tool_call 调用）。"""
        import pathlib
        server = pathlib.Path(__file__).resolve().parents[2] / "server.py"
        text = server.read_text(encoding="utf-8")
        assert "routed_retrieve" in text, "server.py 未注册 RoutedRetrieveTool"

    def test_sys_routed_retrieve_has_production_caller(self):
        """sys_routed_retrieve 必须有非自身的 production caller（RoutedRetrieveTool）。"""
        assert has_production_caller(
            "sys_routed_retrieve", "retrieval.py"
        ), "sys_routed_retrieve() has 0 production callers"

    def test_route_intent_used_by_routed_retrieve(self):
        """_route_intent 意图判定被同文件 sys_routed_retrieve 调用（核心逻辑已接线）。"""
        import ast
        import pathlib
        retrieval = pathlib.Path(__file__).resolve().parents[2] / "harness" / "syscalls" / "retrieval.py"
        tree = ast.parse(retrieval.read_text(encoding="utf-8"))
        routed = next(
            (n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name == "sys_routed_retrieve"), None)
        assert routed is not None, "sys_routed_retrieve 未定义"
        calls = [n.func.id for n in ast.walk(routed) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        assert "_route_intent" in calls, "_route_intent 未被 sys_routed_retrieve 调用"


class TestWebResultQualityWired:

    def test_assess_web_results_has_production_caller(self):
        """assess_web_results 必须有非自身 production caller（sys_routed_retrieve）。"""
        assert has_production_caller(
            "assess_web_results", "web_result_quality.py"
        ), "assess_web_results() has 0 production callers"