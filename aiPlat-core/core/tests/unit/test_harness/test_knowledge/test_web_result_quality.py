"""test_web_result_quality.py — Web 搜索结果可信度评估测试（AnySearch 借鉴 P1-2，2026-08-28）。

覆盖：① 权威域名高可信 ② 低质域名低可信 ③ 结果不足 → 人工复核 ④ 多源一致性奖励
⑤ annotate_results 原地标注。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core.harness.knowledge.web_result_quality import (  # noqa: E402
    assess_web_results, annotate_results, _domain_authority,
)


def test_domain_authority_high():
    """权威域名（官方文档/代码平台）→ 高权威分。"""
    assert _domain_authority("https://docs.python.org/3/library") >= 0.9
    assert _domain_authority("https://github.com/foo/bar") >= 0.9


def test_domain_authority_low():
    """低质域名 → 低权威分。"""
    assert _domain_authority("https://medium.com/@random/post") <= 0.3
    assert _domain_authority("https://some-blog.blogspot.com/x") <= 0.3


def test_assess_pass_with_authoritative_sources():
    """权威源 + 相关证据 → pass（use_results）。"""
    results = [
        {"source_url": "https://docs.python.org/3/library/re.html",
         "evidence_snippet": "python re module regular expression", "source": "ddg_abstract",
         "confidence": 0.7},
        {"source_url": "https://github.com/python/cpython",
         "evidence_snippet": "python regular expression implementation", "source": "ddg_related",
         "confidence": 0.6},
    ]
    r = assess_web_results(results, "python regular expression", threshold=0.4)
    assert r["pass"] is True
    assert r["action"] == "use_results"
    assert r["avg_score"] >= 0.4


def test_assess_flag_for_human_when_insufficient():
    """结果不足 → flag_for_human（人工复核）。"""
    r = assess_web_results([], "query", min_results=2)
    assert r["pass"] is False
    assert r["action"] == "flag_for_human"


def test_assess_cross_source_bonus():
    """多源一致性奖励：source 多样性 → cross_bonus 提升平均分。"""
    results = [
        {"source_url": "https://a.com/x", "evidence_snippet": "topic a b", "source": "ddg_abstract",
         "confidence": 0.5},
        {"source_url": "https://b.com/y", "evidence_snippet": "topic c d", "source": "ddg_related",
         "confidence": 0.5},
    ]
    r = assess_web_results(results, "topic", threshold=0.0)
    # cross_bonus=0.1 → 平均分略高于无 bonus
    assert r["per_result"][0]["quality_score"] >= 0.1


def test_annotate_results():
    """annotate_results → 每条结果带 quality_score/quality_reason。"""
    results = [
        {"source_url": "https://docs.python.org/3", "evidence_snippet": "python docs",
         "source": "ddg_abstract", "confidence": 0.6},
    ]
    out = annotate_results(results, "python")
    assert "quality_score" in out[0]
    assert "quality_reason" in out[0]
