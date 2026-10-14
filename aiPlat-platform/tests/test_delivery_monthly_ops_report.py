"""Offline: L1 monthly ops report composes cost + kb_health without inventing scores."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "aiPlat-platform"))


def test_render_monthly_ops_markdown_soft_unavail():
    from delivery.monthly_ops_report import render_monthly_ops_markdown

    report = {
        "ok": True,
        "period": "2026-10",
        "tenant_id": "t1",
        "window_hours": 720,
        "sku": "L1",
        "generated_at": "2026-10-14T00:00:00+00:00",
        "daemon": {"available": False, "reason": "no store"},
        "cost": {
            "api_calls": {"available": True, "total": 42},
            "cache": {
                "available": True,
                "hits": 10,
                "total_requests": 40,
                "hit_rate_pct": 25.0,
            },
            "model_routing": {"usage_share_available": False, "usage_share_note": "n/a"},
            "empty_intercept": {"available": True, "count": 3},
        },
        "kb_health": {
            "health": {"score": None, "label": "数据不足", "insufficient_data": True},
            "metrics": {"available": True, "total_queries": 0},
            "suggestions": ["维持巡检"],
        },
    }
    md = render_monthly_ops_markdown(report)
    assert "月度运行报告" in md
    assert "unavailable" in md
    assert "数据不足" in md
    assert "不编造" in md
    assert "42" in md
    assert "25.0%" in md or "25%" in md


def test_build_monthly_ops_soft_fail(monkeypatch):
    from delivery import monthly_ops_report as mop

    monkeypatch.setattr(
        mop,
        "_daemon_snapshot",
        lambda: {"available": True, "total_jobs": 2, "running_jobs": 1, "note": "fixture"},
    )
    monkeypatch.setattr(
        "delivery.cost_report.build_delivery_cost_report",
        lambda **kwargs: {
            "api_calls": {"available": False},
            "cache": {"available": False, "reason": "n/a"},
            "model_routing": {"usage_share_available": False},
            "empty_intercept": {"available": False},
        },
    )
    monkeypatch.setattr(
        "delivery.kb_health.build_kb_health_report",
        lambda **kwargs: {
            "health": {"score": 80, "label": "良好", "insufficient_data": False},
            "metrics": {
                "available": True,
                "total_queries": 10,
                "no_answer_rate_pct": 5.0,
                "citation_coverage_pct": 90.0,
            },
            "suggestions": ["补差旅文档"],
        },
    )
    report = mop.build_monthly_ops_report(tenant_id="t", window_hours=24)
    assert report.get("ok") is True
    assert report.get("sku") == "L1"
    md = mop.render_monthly_ops_markdown(report)
    assert "80/100" in md
    assert "补差旅文档" in md
    summary = mop.monthly_ops_summary_lines(report)
    assert "80/100" in summary
    assert "托管任务: 1/2" in summary
