#!/usr/bin/env python3
"""
Kernel metrics / acceptance helper (Phase 3)

Computes measurable metrics from ExecutionStore sqlite DB:
  - trace_id coverage for agent_executions / syscall_events
  - basic counts for approvals, failures

Usage:
  python3 scripts/kernel_metrics.py --db /path/to/aiplat.db --min-trace-coverage 0.99

Exit codes:
  0: OK (threshold met)
  1: Threshold not met
  2: Invalid usage / DB error
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional


def _query_one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
    cur = conn.execute(sql, params)
    return cur.fetchone()


def _coverage(conn: sqlite3.Connection, table: str) -> Dict[str, Any]:
    row = _query_one(
        conn,
        f"""
        SELECT
          COUNT(1) AS total,
          SUM(CASE WHEN trace_id IS NULL OR trace_id='' THEN 1 ELSE 0 END) AS missing_trace
        FROM {table};
        """,
    )
    total = int(row["total"] if row else 0)
    missing = int(row["missing_trace"] if row and row["missing_trace"] is not None else 0)
    ok = max(0, total - missing)
    cov = (ok / total) if total else 1.0
    return {"table": table, "total": total, "missing_trace": missing, "coverage": cov}


def _span_coverage(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    """
    Coverage for syscall_events.span_id and join validity against spans.span_id.
    Only works when schema has syscall_events.span_id (v10+).
    """
    try:
        row = _query_one(
            conn,
            """
            SELECT
              COUNT(1) AS total,
              SUM(CASE WHEN span_id IS NULL OR span_id='' THEN 1 ELSE 0 END) AS missing_span
            FROM syscall_events;
            """,
        )
        total = int(row["total"] if row else 0)
        missing = int(row["missing_span"] if row and row["missing_span"] is not None else 0)
        ok = max(0, total - missing)
        cov = (ok / total) if total else 1.0

        row2 = _query_one(
            conn,
            """
            SELECT
              COUNT(1) AS total,
              SUM(CASE WHEN s.span_id IS NULL THEN 1 ELSE 0 END) AS missing_join
            FROM syscall_events e
            LEFT JOIN spans s ON s.span_id = e.span_id;
            """,
        )
        missing_join = int(row2["missing_join"] if row2 and row2["missing_join"] is not None else 0)

        return {
            "table": "syscall_events",
            "total": total,
            "missing_span_id": missing,
            "span_id_coverage": cov,
            "missing_join_to_spans": missing_join,
        }
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="ExecutionStore sqlite db path")
    ap.add_argument("--min-trace-coverage", type=float, default=0.99)
    ap.add_argument("--min-span-id-coverage", type=float, default=0.99)
    ap.add_argument("--json", action="store_true", help="Output JSON only")
    args = ap.parse_args()

    try:
        conn = sqlite3.connect(args.db)
        conn.row_factory = sqlite3.Row
    except Exception as e:
        print(f"[metrics] failed to open db: {e}", file=sys.stderr)
        return 2

    try:
        agent = _coverage(conn, "agent_executions")
        syscall = _coverage(conn, "syscall_events")
        span_cov = _span_coverage(conn)

        approvals_pending = _query_one(conn, "SELECT COUNT(1) AS c FROM approval_requests WHERE status='pending';")
        approvals_total = _query_one(conn, "SELECT COUNT(1) AS c FROM approval_requests;")

        out = {
            "trace_coverage": {
                "agent_executions": agent,
                "syscall_events": syscall,
            },
            "span_coverage": span_cov,
            "approvals": {
                "pending": int((approvals_pending or {}).get("c", 0) if approvals_pending else 0),
                "total": int((approvals_total or {}).get("c", 0) if approvals_total else 0),
            },
        }

        ok = (agent["coverage"] >= args.min_trace_coverage) and (syscall["coverage"] >= args.min_trace_coverage)
        if span_cov is not None:
            ok = ok and (float(span_cov.get("span_id_coverage") or 1.0) >= args.min_span_id_coverage)
        out["ok"] = ok
        out["min_trace_coverage"] = args.min_trace_coverage
        out["min_span_id_coverage"] = args.min_span_id_coverage

        if args.json:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print("[metrics] trace coverage:")
            print(f"  - agent_executions: {agent['coverage']:.4f} (missing {agent['missing_trace']}/{agent['total']})")
            print(f"  - syscall_events : {syscall['coverage']:.4f} (missing {syscall['missing_trace']}/{syscall['total']})")
            if span_cov is not None:
                print("[metrics] span coverage:")
                print(
                    f"  - syscall_events.span_id: {float(span_cov.get('span_id_coverage') or 1.0):.4f} "
                    f"(missing {span_cov.get('missing_span_id')}/{span_cov.get('total')})"
                )
                print(f"  - syscall_events span join missing: {span_cov.get('missing_join_to_spans')}")
            print(f"[metrics] approvals: pending={out['approvals']['pending']} total={out['approvals']['total']}")
            print(f"[metrics] threshold: min_trace_coverage={args.min_trace_coverage}")
            if span_cov is not None:
                print(f"[metrics] threshold: min_span_id_coverage={args.min_span_id_coverage}")
            print(f"[metrics] ok={ok}")

        return 0 if ok else 1
    except Exception as e:
        print(f"[metrics] failed: {e}", file=sys.stderr)
        return 2
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
