#!/usr/bin/env python3
"""Render delivery COST_REPORT.md (offline fixture or live collect).

Usage:
  PYTHONPATH=aiPlat-platform:aiPlat-core:. \\
    python3 scripts/render_delivery_cost_report.py --out /tmp/COST_REPORT.md
  python3 scripts/render_delivery_cost_report.py --fixture --out /tmp/COST_REPORT.md
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
        "window_hours": 720,
        "api_calls": {"available": True, "total": 1200, "source": "fixture"},
        "cache": {
            "available": True,
            "l1_hits": 300,
            "l2_hits": 100,
            "misses": 800,
            "hits": 400,
            "total_requests": 1200,
            "hit_rate_pct": 33.3,
            "enabled": True,
        },
        "model_routing": {
            "available": True,
            "usage_share_available": False,
            "usage_share_note": "尚无按 purpose 的调用计量；下列为当前分流策略（配置快照），非流量占比",
            "simple_purposes": ["chat", "clarify", "skill_execution"],
            "complex_purposes": ["code_gen", "reasoning", "doc_llm", "eval_code"],
            "purpose_to_model": {
                "chat": "demo-light",
                "code_gen": "demo-heavy",
                "reasoning": "demo-heavy",
            },
        },
        "empty_intercept": {
            "available": True,
            "count": 148,
            "label": "empty_kb_retrieve",
            "note": "窗口内空命中检索次数",
            "proxy": {"label": "kb_no_answer_rate_pct", "value": 12.3},
        },
        "billing": {"available": False, "reason": "fixture"},
        "kb_metrics": {
            "available": True,
            "total_queries": 1200,
            "empty_retrieve_count": 148,
            "no_answer_rate_pct": 12.3,
        },
        "cny_estimate": None,
        "spec": "HYBRID_ENTERPRISE_DELIVERY.md §4",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--tenant-id", default="default")
    ap.add_argument("--project-id", default="")
    ap.add_argument("--window-hours", type=int, default=720)
    ap.add_argument("--fixture", action="store_true", help="Skip live collect; use sample numbers")
    ap.add_argument("--json-out", type=Path, default=None, help="Also write raw JSON")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    for p in (root / "aiPlat-platform", root / "aiPlat-core", root):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)

    from delivery.cost_report import build_delivery_cost_report, render_cost_report_markdown

    if args.fixture:
        report = _fixture_report()
    else:
        report = build_delivery_cost_report(
            tenant_id=args.tenant_id,
            window_hours=args.window_hours,
            project_id=args.project_id,
        )
    md = render_cost_report_markdown(report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md, encoding="utf-8")
    if args.json_out:
        args.json_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps({"ok": True, "out": str(args.out), "api_calls": report.get("api_calls")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
