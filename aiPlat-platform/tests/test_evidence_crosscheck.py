"""test_evidence_crosscheck.py — 证据校验器"外部事实交叉"测试（防自洽的谎言）。

覆盖：路径存在/缺失判定、无引号 pattern 跳过、glob 跳过、管道/重定向过滤。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1].parent
_SPEC = importlib.util.spec_from_file_location(
    "verify_claude_md_evidence", ROOT / "scripts/verify_claude_md_evidence.py")
_ev = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_ev)

cross_check_paths = _ev._cross_check_paths


def test_existing_path_reports_exists():
    r = cross_check_paths("grep -rn 'tenant_id: str' aiPlat-core/core/harness/knowledge/types.py")
    assert r and r[0]["target"] == "aiPlat-core/core/harness/knowledge/types.py"
    assert r[0]["exists"] is True


def test_missing_path_detected():
    """A2 场景：grep 基于不存在的文件自证通过 → cross_check 必须抓到。"""
    r = cross_check_paths("grep -rn 'from core.harness' aiPlat-platform/does/not/exist.py")
    assert r and r[0]["exists"] is False


def test_unquoted_pattern_skipped():
    """无引号 pattern（grep -c xxx file）无法可靠区分 → 跳过而非误报。"""
    assert cross_check_paths("grep -c start_sla_monitor aiPlat-core/core/server.py") == []


def test_glob_path_skipped():
    """glob（shell 展开）Path 不展开 → 跳过。"""
    assert cross_check_paths("grep -rl 'execution_type:' aiPlat-core/core/engine/skills/*/SKILL.md") == []


def test_pipe_first_segment_only():
    r = cross_check_paths("grep -rn 'response_model=dict' aiPlat-platform/ | grep -v '# noqa' | wc -l")
    assert len(r) == 1 and r[0]["target"] == "aiPlat-platform/"


def test_redirect_token_filtered():
    r = cross_check_paths("grep -rn 'xxx' aiPlat-core/ 2>/dev/null | wc -l")
    # 重定向 token 被过滤；合法路径 aiPlat-core/ 保留
    assert len(r) == 1 and r[0]["target"] == "aiPlat-core/"
    assert not any("2>" in c["target"] for c in r)


def test_non_grep_command_skipped():
    assert cross_check_paths("python3 -c \"print(1)\"") == []
