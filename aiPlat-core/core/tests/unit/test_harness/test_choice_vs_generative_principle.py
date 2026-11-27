"""选择题原则守卫：固定选项不得默走生成式 LLM 热路径。

依据：docs/architecture/plans/ollaya-decision-layer-implementation-plan.md §0.1
≠ 采样 Go；≠ 挂 classify；≠ Ollaya 准确率。
"""

from __future__ import annotations

import re
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[3]  # aiPlat-core/core


def _iter_py_files():
    for p in CORE_ROOT.rglob("*.py"):
        if "tests" in p.parts or ".venv" in p.parts:
            continue
        yield p


def test_classify_with_llm_has_no_production_callers():
    """生产代码不得调用 classify_with_llm（仅允许定义处）。"""
    call_re = re.compile(r"\bclassify_with_llm\s*\(")
    offenders: list[str] = []
    for path in _iter_py_files():
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if "def classify_with_llm" in line:
                continue
            if call_re.search(line):
                offenders.append(f"{path.relative_to(CORE_ROOT)}:{i}:{line.strip()}")
    assert offenders == [], (
        "选择题原则：勿把 classify_with_llm 接成热路径；命中:\n"
        + "\n".join(offenders)
    )


def test_domain_router_still_last_resort_t3_only():
    """DomainRouter 仍为 T1→T2→T3；禁止在 classify 里 await decision 服务。"""
    src = (CORE_ROOT / "harness/knowledge/domain_router.py").read_text(encoding="utf-8")
    assert "def classify(" in src
    assert "_llm_classify" in src
    assert "await " not in src.split("def classify(")[1].split("def suggest(")[0]
    # 钩子未接线：classify 体不得引用 decision_shadow
    classify_body = src.split("def classify(")[1].split("def suggest(")[0]
    assert "decision_shadow" not in classify_body
