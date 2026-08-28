"""test_diag_blocking_fix.py — 诊断端点事件循环阻塞修复回归测试（2026-08-28）。

覆盖 502 根因链修复：
① system_health.py 的 logging 必须在模块级（docstring 之外）——避免 except 分支 NameError
② 慢诊断端点必须为同步 def（FastAPI 线程池），禁止 async def 内同步重活阻塞事件循环
③ config_drift_detector 对 ModelManager 候选列表必须复用（缓存），禁止逐 agent 实例化
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

_CORE_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(_CORE_ROOT))


def _first_def_arg_names(func_node: ast.FunctionDef) -> list:
    return [a.arg for a in func_node.args.args]


def _module_functions(src_path: str) -> dict:
    tree = ast.parse(Path(src_path).read_text(encoding="utf-8"))
    return {
        n.name: n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_system_health_logging_imported_at_module_level():
    """import logging 必须在模块级（docstring 之外）——修复前误入 docstring 导致 except 分支 NameError。"""
    src_path = _CORE_ROOT / "core/harness/evaluation/system_health.py"
    src = src_path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    module_logging = any(
        isinstance(n, ast.Import) and any(a.name == "logging" for a in n.names)
        for n in tree.body
    )
    assert module_logging, "system_health.py 模块级必须 import logging（修复前误入 docstring）"
    # 运行时验证
    import core.harness.evaluation.system_health as sh
    assert hasattr(sh, "logging")


def test_slow_diag_endpoints_are_sync_def():
    """慢诊断端点必须为同步 def——修复前 async def 内同步重活阻塞 uvicorn 事件循环。"""
    src_path = _CORE_ROOT / "core/api/routers/diagnostics.py"
    funcs = _module_functions(str(src_path))
    for name in (
        "get_system_health",
        "get_adoption_metrics",
        "get_ontology_audit",
        "get_ontology_audit_summary",
        "get_drift_status",
    ):
        node = funcs.get(name)
        assert node is not None, f"{name} 不存在"
        assert isinstance(node, ast.FunctionDef), (
            f"{name} 必须是同步 def（FastAPI 线程池执行）；修复前为 async def 阻塞事件循环"
        )


def test_drift_scan_reuses_model_candidates():
    """config_drift_detector 对 ModelManager 候选列表必须缓存复用——禁止逐 agent 实例化（每实例 4.7-5.1s）。"""
    src_path = _CORE_ROOT / "core/harness/evaluation/config_drift_detector.py"
    src = src_path.read_text(encoding="utf-8")
    assert "_cached_chat_candidates" in src, (
        "scan_all_agents 必须缓存 ModelManager 候选列表（_cached_chat_candidates）"
    )
    # 运行时验证:模块可导入且 ConfigDriftDetector 可实例化（不触发 ModelManager 首查）
    from core.harness.evaluation.config_drift_detector import ConfigDriftDetector

    cd = ConfigDriftDetector()
    assert hasattr(cd, "_agents_dir")
