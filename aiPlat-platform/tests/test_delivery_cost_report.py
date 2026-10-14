"""Offline: delivery cost report narrative without live platform."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "aiPlat-platform"))


def test_render_cost_report_markdown_no_fake_cny():
    from delivery.cost_report import render_cost_report_markdown

    report = {
        "ok": True,
        "generated_at": "2026-10-14T00:00:00+00:00",
        "tenant_id": "t1",
        "project_id": "p1",
        "window_hours": 720,
        "api_calls": {"available": True, "total": 10, "source": "fixture"},
        "cache": {
            "available": True,
            "hits": 4,
            "total_requests": 10,
            "hit_rate_pct": 40.0,
            "l1_hits": 3,
            "l2_hits": 1,
            "misses": 6,
        },
        "model_routing": {
            "available": True,
            "usage_share_note": "配置快照",
            "simple_purposes": ["chat"],
            "complex_purposes": ["code_gen"],
            "purpose_to_model": {"chat": "m1", "code_gen": "m2"},
        },
        "empty_intercept": {
            "available": False,
            "reason": "待补",
            "proxy": {"label": "kb_no_answer_rate_pct", "value": 1.0},
        },
        "billing": {"available": False},
        "cny_estimate": None,
    }
    md = render_cost_report_markdown(report)
    assert "成本页" in md
    assert "40.0%" in md or "40%" in md
    assert "未配置单价" in md
    assert "流量占比" in md
    assert "estimated_saved_cny" not in md
    assert "缓存节省估算" not in md


def test_optional_cny_only_with_env(monkeypatch):
    from delivery import cost_report as cr

    monkeypatch.delenv("AIPLAT_DELIVERY_COST_CNY_PER_CACHE_HIT", raising=False)
    assert cr._optional_cny_saved({"available": True, "hits": 10}) is None
    monkeypatch.setenv("AIPLAT_DELIVERY_COST_CNY_PER_CACHE_HIT", "0.5")
    got = cr._optional_cny_saved({"available": True, "hits": 10})
    assert got is not None
    assert got["estimated_saved_cny"] == 5.0


def test_build_report_soft_fail():
    """build_delivery_cost_report must return ok even if subsystems missing."""
    from delivery.cost_report import build_delivery_cost_report

    report = build_delivery_cost_report(tenant_id="offline-test", window_hours=24)
    assert report.get("ok") is True
    assert "cache" in report
    assert "model_routing" in report
    md = __import__("delivery.cost_report", fromlist=["render_cost_report_markdown"]).render_cost_report_markdown(
        report
    )
    assert "交付报告" in md
