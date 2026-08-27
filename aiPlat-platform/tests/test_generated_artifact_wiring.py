"""test_generated_artifact_wiring.py — 生成物适用性守卫逻辑测试。

覆盖：模块发现（顶层 .py + 子目录）、Rule A（无条目）、Rule B（缺"生成物"标注）、通过场景。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1].parent
_SPEC = importlib.util.spec_from_file_location(
    "check_generated_artifact_wiring", ROOT / "scripts/check_generated_artifact_wiring.py")
_ga = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_ga)


def test_discover_modules():
    """扫真实 governance/：顶层 .py + 有 __init__.py 的子目录均为模块。"""
    mods = _ga.discover_modules()
    for expected in ("agent_messages", "daemon_jobs", "eval_observability",
                     "experience_feedback", "audit", "quota", "rate_limit"):
        assert expected in mods, f"missing {expected}"
    assert "__init__" not in mods


def test_rule_a_missing_entry():
    caps = "| 其他能力 | path | ✅ | 描述 | 已合入 |\n"
    v = _ga.check(caps, ["daemon_jobs"])
    assert len(v) == 1 and "Rule A" in v[0]


def test_rule_b_missing_artifact_mark():
    caps = "| 后台任务托管 | governance/daemon_jobs.py | ✅ | 描述缺适用性声明 | 已合入 |\n"
    v = _ga.check(caps, ["daemon_jobs"])
    assert len(v) == 1 and "Rule B" in v[0]


def test_pass_with_artifact_mark():
    caps = ("| 后台任务托管 | governance/daemon_jobs.py | ✅ | "
            "描述；生成物适用：待接线 | 已合入 |\n")
    assert _ga.check(caps, ["daemon_jobs"]) == []
