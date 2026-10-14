#!/usr/bin/env python3
"""Render KB health delivery page (offline fixture or live meters)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
PLATFORM = WORKSPACE / "aiPlat-platform"
if str(PLATFORM) not in sys.path:
    sys.path.insert(0, str(PLATFORM))


def main() -> int:
    ap = argparse.ArgumentParser(description="Render delivery KB health markdown")
    ap.add_argument("--out", type=Path, default=Path("KB_HEALTH.md"))
    ap.add_argument("--tenant-id", default="default")
    ap.add_argument("--collection-id", default="default")
    ap.add_argument("--project-id", default="")
    ap.add_argument("--window-hours", type=int, default=168)
    ap.add_argument(
        "--fixture",
        action="store_true",
        help="Skip live meters; write a demo report",
    )
    args = ap.parse_args()

    from delivery.kb_health import (
        build_kb_health_report,
        kb_health_score,
        render_kb_health_markdown,
    )

    if args.fixture:
        metrics = {
            "available": True,
            "total_queries": 1234,
            "no_answer_rate_pct": 12.3,
            "citation_coverage_pct": 87.7,
            "error_correction_rate_pct": 2.1,
            "repeat_question_rate_pct": 8.2,
            "approval_trigger_rate_pct": 1.5,
            "permission_blocks": 0,
            "gap_repair_cycles": [],
        }
        report = {
            "ok": True,
            "generated_at": "2026-10-14T00:00:00+00:00",
            "tenant_id": args.tenant_id,
            "project_id": args.project_id or "sample",
            "collection_id": args.collection_id,
            "window_hours": args.window_hours,
            "health": kb_health_score(metrics),
            "metrics": metrics,
            "stats": {"available": True, "documents": 156, "elements": 0, "embeddings": 0, "collections": 1},
            "docs_this_week": {"available": True, "count": 12, "collection_id": args.collection_id},
            "cache": {
                "available": True,
                "hits": 420,
                "total_requests": 1234,
                "hit_rate_pct": 34.0,
            },
            "miss_top": {
                "available": True,
                "items": [
                    {"question": "差旅报销标准", "count": 3},
                    {"question": "年假折算规则", "count": 2},
                ],
            },
            "low_confidence_top": {
                "available": True,
                "items": [{"question": "公积金提取条件", "score": 0.41}],
            },
            "suggestions": [
                "建议补充「差旅报销标准」「年假折算规则」相关文档（来自漏召 TOP）"
            ],
            "spec": "packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE_KB_HEALTH.md",
        }
    else:
        report = build_kb_health_report(
            tenant_id=args.tenant_id,
            collection_id=args.collection_id,
            window_hours=args.window_hours,
            project_id=args.project_id,
        )

    md = render_kb_health_markdown(report)
    args.out.write_text(md, encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "score": (report.get("health") or {}).get("score"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
