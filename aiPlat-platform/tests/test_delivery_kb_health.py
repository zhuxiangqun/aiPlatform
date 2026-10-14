"""Unit tests for KB health score + markdown (HYBRID_ENTERPRISE_KB_HEALTH)."""
from __future__ import annotations

from unittest.mock import patch

from delivery.kb_health import (
    build_kb_health_report,
    kb_health_score,
    kb_low_confidence_top,
    kb_miss_top,
    render_kb_health_markdown,
    render_kb_health_plain,
)


def test_kb_health_score_bands():
    excellent = kb_health_score(
        {
            "total_queries": 200,
            "citation_coverage_pct": 95,
            "no_answer_rate_pct": 5,
            "error_correction_rate_pct": 2,
            "repeat_question_rate_pct": 3,
        }
    )
    assert excellent["score"] >= 85
    assert excellent["label"] == "优秀"
    assert excellent["band"] == "green"

    risk = kb_health_score(
        {
            "total_queries": 200,
            "citation_coverage_pct": 10,
            "no_answer_rate_pct": 80,
            "error_correction_rate_pct": 50,
            "repeat_question_rate_pct": 40,
        }
    )
    assert risk["score"] < 55
    assert risk["label"] == "风险"


def test_kb_health_score_boundary_70():
    # Tuned to land near 70–84 "良好"
    mid = kb_health_score(
        {
            "total_queries": 100,
            "citation_coverage_pct": 70,
            "no_answer_rate_pct": 20,
            "error_correction_rate_pct": 10,
            "repeat_question_rate_pct": 10,
        }
    )
    assert 55 <= mid["score"] <= 84


def test_kb_health_score_zero_traffic_insufficient():
    z = kb_health_score(
        {
            "total_queries": 0,
            "citation_coverage_pct": 0,
            "no_answer_rate_pct": 0,
            "error_correction_rate_pct": 0,
            "repeat_question_rate_pct": 0,
        }
    )
    assert z["score"] is None
    assert z["label"] == "数据不足"
    assert z["band"] == "gray"
    assert z.get("insufficient_data") is True


def test_render_markdown_has_suggestions():
    report = {
        "ok": True,
        "generated_at": "2026-10-14T00:00:00+00:00",
        "tenant_id": "demo",
        "collection_id": "default",
        "window_hours": 168,
        "health": {"score": 82, "label": "良好", "band": "blue"},
        "metrics": {
            "available": True,
            "total_queries": 100,
            "no_answer_rate_pct": 12.3,
            "citation_coverage_pct": 87.7,
            "error_correction_rate_pct": 2.1,
            "repeat_question_rate_pct": 8.2,
            "approval_trigger_rate_pct": 1.5,
            "permission_blocks": 0,
        },
        "stats": {"available": True, "documents": 156},
        "docs_this_week": {"available": True, "count": 12},
        "cache": {"available": True, "hit_rate_pct": 34.0, "hits": 40, "total_requests": 120},
        "miss_top": {
            "available": True,
            "items": [{"question": "差旅报销标准", "count": 3}],
        },
        "low_confidence_top": {"available": True, "items": []},
        "suggestions": ["建议补充「差旅报销标准」相关文档（来自漏召 TOP）"],
    }
    md = render_kb_health_markdown(report)
    assert "知识库健康分: 82/100" in md
    assert "差旅报销标准" in md
    assert "建议" in md
    plain = render_kb_health_plain(report)
    assert "82/100" in plain
    assert "建议" in plain


def test_build_report_soft_fail():
    report = build_kb_health_report(tenant_id="offline-test", window_hours=24)
    assert report.get("ok") is True
    assert "health" in report
    assert "score" in report["health"]
    assert isinstance(report.get("suggestions"), list)


def test_kb_miss_top_and_low_public_wrappers():
    miss = {
        "available": True,
        "items": [{"question": "差旅", "count": 2}],
        "window_hours": 24,
    }
    low = {
        "available": True,
        "items": [{"question": "年假", "score": 0.2}],
        "window_hours": 24,
        "threshold": 0.5,
    }
    with patch("delivery.kb_health._miss_and_low_top", return_value=(miss, low)):
        assert kb_miss_top(window_hours=24, limit=5)["items"][0]["question"] == "差旅"
        assert kb_low_confidence_top(window_hours=24, threshold=0.5)["items"][0]["score"] == 0.2
