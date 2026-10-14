"""Offline: L3 duty desk soft-fails and never invents contact/iteration history."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "aiPlat-platform"))


def test_render_l3_duty_markdown_unavailable_honest():
    from delivery.l3_duty_desk import render_l3_duty_markdown

    report = {
        "ok": True,
        "generated_at": "2026-10-14T00:00:00+00:00",
        "tenant_id": "t1",
        "window_hours": 720,
        "period": "2026-Q4",
        "sku": "L3",
        "duty_contact": {"available": False, "reason": "未配置"},
        "eval": {"available": False, "reason": "offline"},
        "kb_signals": {"available": False, "reason": "offline"},
        "iterations": {"available": False, "items": [], "reason": "无记录"},
        "quarterly_suggestions": ["维持 L2 入库与巡检"],
    }
    md = render_l3_duty_markdown(report)
    assert "L3 专属值班台" in md
    assert "unavailable" in md
    assert "不编造联系人" in md
    assert "季度建议" in md


def test_build_l3_duty_soft_fail(monkeypatch):
    from delivery import l3_duty_desk as desk

    monkeypatch.delenv("AIPLAT_L3_DUTY_CONTACT", raising=False)
    monkeypatch.delenv("AIPLAT_L3_DUTY_CHANNEL", raising=False)
    monkeypatch.setattr(
        desk,
        "_eval_snapshot",
        lambda: {"available": False, "reason": "test"},
    )
    monkeypatch.setattr(
        desk,
        "_kb_signals",
        lambda **kwargs: {"available": False, "reason": "test"},
    )
    report = desk.build_l3_duty_desk(tenant_id="t", window_hours=24)
    assert report.get("ok") is True
    assert report.get("sku") == "L3"
    assert report["duty_contact"].get("available") is False
    md = desk.render_l3_duty_markdown(report)
    assert "专属值班" in md
    summary = desk.l3_duty_summary_lines(report)
    assert "值班入口" in summary


def test_contact_from_env(monkeypatch):
    from delivery import l3_duty_desk as desk

    monkeypatch.setenv("AIPLAT_L3_DUTY_CONTACT", "ops@example.com")
    monkeypatch.setenv("AIPLAT_L3_DUTY_CHANNEL", "飞书值班群")
    monkeypatch.setenv("AIPLAT_L3_DUTY_HOURS", "工作日 9-18")
    c = desk._duty_contact()
    assert c["available"] is True
    assert c["contact"] == "ops@example.com"
    report = {
        "ok": True,
        "generated_at": "t",
        "tenant_id": "t",
        "window_hours": 24,
        "period": "2026-Q4",
        "sku": "L3",
        "duty_contact": c,
        "eval": {"available": False, "reason": "n/a"},
        "kb_signals": {"available": False, "reason": "n/a"},
        "iterations": {"available": False, "items": [], "reason": "n/a"},
        "quarterly_suggestions": ["配置已就绪"],
    }
    md = desk.render_l3_duty_markdown(report)
    assert "ops@example.com" in md
    assert "飞书值班群" in md
