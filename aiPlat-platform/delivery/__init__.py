"""Delivery report helpers (cost narrative, KB health) — platform layer, no Core harness."""

from .cost_report import (
    build_delivery_cost_report,
    kb_cache_stats,
    render_cost_report_markdown,
)
from .kb_health import (
    build_kb_health_report,
    kb_health_score,
    kb_low_confidence_top,
    kb_miss_top,
    render_kb_health_markdown,
    render_kb_health_plain,
)
from .kb_health_archive import archive_kb_health_report, list_kb_health_archives
from .monthly_ops_report import (
    build_monthly_ops_report,
    monthly_ops_summary_lines,
    render_monthly_ops_markdown,
)
from .l3_duty_desk import (
    build_l3_duty_desk,
    l3_duty_summary_lines,
    render_l3_duty_markdown,
)

__all__ = [
    "build_delivery_cost_report",
    "kb_cache_stats",
    "render_cost_report_markdown",
    "build_kb_health_report",
    "kb_health_score",
    "kb_miss_top",
    "kb_low_confidence_top",
    "render_kb_health_markdown",
    "render_kb_health_plain",
    "archive_kb_health_report",
    "list_kb_health_archives",
    "build_monthly_ops_report",
    "render_monthly_ops_markdown",
    "monthly_ops_summary_lines",
    "build_l3_duty_desk",
    "render_l3_duty_markdown",
    "l3_duty_summary_lines",
]
