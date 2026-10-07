"""Production-depth diagnostic check for one-click / scheduled diagnostics.

Wraps harness.observability.production_depth.build_production_depth_report.
"""

from __future__ import annotations

from typing import Any, Dict


async def check_production_depth() -> Dict[str, Any]:
    from core.harness.observability.production_depth import build_production_depth_report

    report = build_production_depth_report()
    status = str(report.get("status") or "warn")
    if status not in ("pass", "warn", "fail"):
        status = "warn"
    failed = [
        c for c in (report.get("checks") or [])
        if isinstance(c, dict) and c.get("status") in ("warn", "fail")
    ]
    return {
        "status": status,
        "score": report.get("score", 0),
        "summary": report.get("summary"),
        "profile": report.get("profile"),
        "issues": [
            {
                "id": c.get("id"),
                "title": c.get("title"),
                "severity": c.get("status"),
                "hint": c.get("hint"),
            }
            for c in failed
        ],
        "href": "/diagnostics/production-depth",
    }
