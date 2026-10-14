"""Delivery report helpers (cost narrative, KB health) — platform layer, no Core harness."""

from .cost_report import build_delivery_cost_report, render_cost_report_markdown
from .kb_health import (
    build_kb_health_report,
    kb_health_score,
    render_kb_health_markdown,
    render_kb_health_plain,
)

__all__ = [
    "build_delivery_cost_report",
    "render_cost_report_markdown",
    "build_kb_health_report",
    "kb_health_score",
    "render_kb_health_markdown",
    "render_kb_health_plain",
]
