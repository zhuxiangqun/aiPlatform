#!/usr/bin/env python3
"""Offline smoke: cost report prefers LLM syscall purpose share.

Seeds a temp executions DB with purpose-tagged llm success events, then asserts
``usage_share_source=llm_syscall`` and markdown shows 完成调用.

Usage:
  PYTHONPATH=aiPlat-platform:aiPlat-core:. python3 scripts/smoke_delivery_purpose_share.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    for p in (root / "aiPlat-platform", root / "aiPlat-core", root):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)

    with tempfile.TemporaryDirectory(prefix="aiplat-purpose-smoke-") as tmp:
        tmp_p = Path(tmp)
        db = tmp_p / "aiplat_executions.sqlite3"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE syscall_events ("
            "kind TEXT, name TEXT, status TEXT, args_json TEXT, created_at REAL)"
        )
        now = time.time()
        for purpose, n in (("chat", 2), ("code_gen", 1), ("doc_llm", 1)):
            for _ in range(n):
                conn.execute(
                    "INSERT INTO syscall_events(kind,name,status,args_json,created_at) "
                    "VALUES (?,?,?,?,?)",
                    (
                        "llm",
                        "generate",
                        "success",
                        json.dumps(
                            {"prompt_type": "messages", "purpose": purpose},
                            ensure_ascii=False,
                        ),
                        now - 10,
                    ),
                )
        conn.commit()
        conn.close()

        os.environ["AIPLAT_EXECUTION_DB"] = str(db)
        os.environ["AIPLAT_HOME"] = str(tmp_p)

        from delivery.cost_report import (
            build_delivery_cost_report,
            render_cost_report_markdown,
        )

        report = build_delivery_cost_report(tenant_id="smoke", window_hours=24)
        mr = report.get("model_routing") or {}
        if not mr.get("usage_share_available"):
            print(json.dumps({"ok": False, "error": "usage_share_available=False", "mr": mr}))
            return 1
        if mr.get("usage_share_source") != "llm_syscall":
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "expected llm_syscall",
                        "got": mr.get("usage_share_source"),
                    }
                )
            )
            return 1
        if int(mr.get("selection_total") or 0) != 4:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "selection_total",
                        "got": mr.get("selection_total"),
                    }
                )
            )
            return 1
        md = render_cost_report_markdown(report)
        if "完成调用" not in md or "真实 LLM 完成调用" not in md:
            print(json.dumps({"ok": False, "error": "markdown missing completion labels"}))
            return 1

        print(
            json.dumps(
                {
                    "ok": True,
                    "usage_share_source": mr.get("usage_share_source"),
                    "selection_total": mr.get("selection_total"),
                    "purpose_share_pct": mr.get("purpose_share_pct"),
                },
                ensure_ascii=False,
            )
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
