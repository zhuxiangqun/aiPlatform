"""test_pipeline_context_clean.py — 流水线上下文纯净性回归测试（2026-08-28）。

覆盖 PRD 污染修复：产品流水线的上下文组装（assemble_pipeline_context）
不得注入 FDE 诊断专用语义（诊断自优化/业务语义字典/FDE 交付跟踪）——
这些引用 FDE 报告章节（§1/§6/§7/§4.6 ROI），注入产品流水线会污染 PRD/
架构/代码产物（实测视频解析平台 PRD 混入「诊断自优化 (250条历史)」并
产出空壳字段）。
"""
from __future__ import annotations

import sys
from pathlib import Path

_CORE_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_CORE_ROOT))


def test_assemble_pipeline_context_injects_nothing():
    """流水线上下文必须为空——不得注入 FDE 诊断层。"""
    from core.harness.knowledge.context_bus import assemble_pipeline_context

    parts: list = []
    assemble_pipeline_context(
        {"description": "构建一个视频解析平台", "prd_title": "视频解析平台"},
        parts,
    )
    text = "\n".join(parts)
    # 不应包含 FDE 诊断语义
    assert "诊断自优化" not in text
    assert "业务语义字典" not in text
    assert "FDE 交付跟踪" not in text
    assert "§1" not in text and "§7" not in text
    # 修复后流水线注入为空（领域上下文由 DomainRouter 域 prompt 承担）
    assert len(parts) == 0, f"流水线上下文应为空,实际注入: {parts[:3]}"


def test_pipeline_engine_context_block_references_clean_assembler():
    """pipeline_engine 的 3.5b 上下文注入必须调用纯净的 assemble_pipeline_context,
    且空结果不会附加 '## system knowledge context' 标题。"""
    src = (_CORE_ROOT / "core/harness/execution/pipeline_engine.py").read_text(
        encoding="utf-8"
    )
    assert "assemble_pipeline_context(" in src
    # 空内容保护仍存在:只有 _cb_text 非空才附加标题
    assert 'if _cb_text:' in src
