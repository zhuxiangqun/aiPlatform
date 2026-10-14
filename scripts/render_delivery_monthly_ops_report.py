#!/usr/bin/env python3
"""Render delivery MONTHLY_OPS_REPORT.md (offline fixture or live collect).

Usage:
  PYTHONPATH=aiPlat-platform:aiPlat-core:. \\
    python3 scripts/render_delivery_monthly_ops_report.py --out /tmp/MONTHLY_OPS_REPORT.md
  python3 scripts/render_delivery_monthly_ops_report.py --fixture --out /tmp/MONTHLY_OPS_REPORT.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _fixture_report() -> dict:
    return {
        "ok": True,
        "generated_at": "2026-10-14T00:00:00+00:00",
        "tenant_id": "demo",
        "project_id": "sample",
        "collection_id": "default",
        "window_hours": 720,
        "period": "2026-10",
        "sku": "L1",
        "daemon": {
            "available": True,
            "total_jobs": 3,
            "running_jobs": 2,
            "note": "fixture",
        },
        "cost": {
            "ok": True,
            "api_calls": {"available": True, "total": 1200},
            "cache": {
                "available": True,
                "hits": 400,
                "total_requests": 1200,
                "hit_rate_pct": 33.3,
            },
            "model_routing": {
                "usage_share_available": True,
                "usage_share_source": "llm_syscall",
                "selection_total": 100,
                "bucket_share_pct": {"simple": 60.0, "complex": 40.0, "other": 0.0},
            },
            "empty_intercept": {"available": True, "count": 12},
        },
        "kb_health": {
            "ok": True,
            "health": {"score": 82, "label": "良好", "insufficient_data": False},
            "metrics": {
                "total_queries": 200,
                "no_answer_rate_pct": 8.0,
                "citation_coverage_pct": 75.0,
            },
            "suggestions": ["补充「差旅报销标准」文档"],
        },
        "spec": "HYBRID_ENTERPRISE_DELIVERY.md §5 L1",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--tenant-id", default="default")
    ap.add_argument("--project-id", default="")
    ap.add_argument("--collection-id", default="default")
    ap.add_argument("--window-hours", type=int, default=720)
    ap.add_argument("--fixture", action="store_true")
    ap.add_argument("--json-out", type=Path, default=None)
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    for p in (root / "aiPlat-platform", root / "aiPlat-core", root):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)

    if args.fixture:
        report = _fixture_report()
    else:
        from delivery.monthly_ops_report import build_monthly_ops_report

        report = build_monthly_ops_report(
            tenant_id=args.tenant_id,
            window_hours=args.window_hours,
            project_id=args.project_id,
            collection_id=args.collection_id,
        )

    from delivery.monthly_ops_report import render_monthly_ops_markdown

    md = render_monthly_ops_markdown(report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md, encoding="utf-8")
    if args.json_out:
        args.json_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"wrote {args.out} ({len(md)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
