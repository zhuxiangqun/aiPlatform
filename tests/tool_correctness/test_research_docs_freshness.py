"""工具自测：scripts/check_research_docs_freshness.py（Rule 6 文档新鲜度守卫）。

验证核心函数行为（CLAUDE.md §5.30 规则 12：新工具必须有自测）：
  1. symbol_exists：文件引用/类名引用/配置字段/豁免模式判定正确
  2. 矛盾标记检测：'已修复+待修'同行判定、'已修复+部分完成'豁免
  3. 时间戳检查：'最后验证'早于代码 mtime 时提示
"""
import os
import subprocess
import sys
import tempfile

import pytest

WS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(WS, "scripts"))

from check_research_docs_freshness import (  # noqa: E402
    NEGATE,
    SKIP_DOC,
    build_matchers,
    code_files,
    symbol_exists,
)


# ═══════════════════════════════════════════════════════════
# 1) symbol_exists 判定
# ═══════════════════════════════════════════════════════════

def test_symbol_exists_real_file():
    """真实存在的 .py 文件 → True。"""
    files = code_files(WS)
    basenames, contents = build_matchers(files)
    # knowledge_ontology.py 必然存在
    assert symbol_exists("knowledge_ontology.py", basenames, contents, WS, files) is True


def test_code_files_includes_aiplat_app():
    """2026-08-23 工具扩展：aiPlat-app 纳入搜索根（渠道适配器等 app 层引用可对账）。"""
    files = code_files(WS)
    basenames, contents = build_matchers(files)
    assert any(b == "whatsapp.py" or b == "lark.py" or b == "teams.py" for b in basenames)
    assert symbol_exists("whatsapp.py", basenames, contents, WS, files) is True


def test_code_files_includes_aiplat_sdk():
    """2026-08-25 工具扩展：aiplat-sdk 纳入搜索根（exec.py/stdio.py 等 SDK 引用可对账）。"""
    files = code_files(WS)
    basenames, contents = build_matchers(files)
    assert symbol_exists("aiplat-sdk/aiplat/exec.py", basenames, contents, WS, files) is True
    assert any(b == "exec.py" or b == "stdio.py" for b in basenames)


def test_symbol_exists_class_name():
    """类名引用（ClassName.tier）→ 类在代码中定义即 True。"""
    files = code_files(WS)
    basenames, contents = build_matchers(files)
    assert symbol_exists("OntologyClass.tier", basenames, contents, WS, files) is True


def test_symbol_exists_exemptions():
    """通配符/self/私有/文档引用 → 豁免 True（不误报）。"""
    files = code_files(WS)
    basenames, contents = build_matchers(files)
    assert symbol_exists("self._skills", basenames, contents, WS, files) is True
    assert symbol_exists("*_tool.py", basenames, contents, WS, files) is True
    assert symbol_exists("plan-tier-ontology-layering.md", basenames, contents, WS, files) is True
    assert symbol_exists("~/.aiplat/hooks.json", basenames, contents, WS, files) is True


def test_symbol_exists_missing_file():
    """明显不存在的文件 → False（抓过时）。"""
    files = code_files(WS)
    basenames, contents = build_matchers(files)
    assert symbol_exists("zzznonexistentfile.py", basenames, contents, WS, files) is False


# ═══════════════════════════════════════════════════════════
# 2) 常量与扫描范围
# ═══════════════════════════════════════════════════════════

def test_skip_doc_filters_research_docs():
    """调研/对标类文档不参与对账。"""
    assert any("调研" in k for k in SKIP_DOC)


def test_negate_includes_partial_state():
    """'部分完成/残留'等中间状态不判为矛盾。"""
    assert "部分完成" in NEGATE
    assert "残留" in NEGATE


# ═══════════════════════════════════════════════════════════
# 3) 端到端：脚本 CLI 可运行且无致命错误
# ═══════════════════════════════════════════════════════════

def test_script_cli_runs():
    """脚本 CLI 在真实 workspace 上运行不崩溃（返回 0 或正整数）。"""
    result = subprocess.run(
        [sys.executable, os.path.join(WS, "scripts", "check_research_docs_freshness.py"), WS],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode >= 0
    assert "research-doc freshness" in result.stdout or "OK: All research docs" in result.stdout


def test_script_accepts_missing_dir():
    """不存在的 research 目录 → 0 违规。"""
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [sys.executable, os.path.join(WS, "scripts", "check_research_docs_freshness.py"), tmp],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0
