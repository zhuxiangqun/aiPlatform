#!/usr/bin/env python3
"""Ollaya Phase 0 — scrape DomainRouter route_stats for the baseline evidence table.

Fetches GET {base}/api/core/diagnostics/domain-router/route-stats from one or more
core bases, optionally appends JSONL, prints a markdown table row.

Honesty:
  - Process-scoped counters; restart clears; multi-replica = sum manually / multi --base
  - ≠ Ollaya accuracy; ≠ decision_shadow; ≠ Go Phase 1
  - Empty/zero on a freshly started process is expected, not a green light
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_PATH = "/api/core/diagnostics/domain-router/route-stats"
HONESTY = (
    "process scope only; restart clears; ≠ Ollaya accuracy; "
    "≠ decision_shadow; ≠ Go Phase 1"
)


def _fetch(url: str, timeout: float) -> Dict[str, Any]:
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    data = json.loads(raw) if raw else {}
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object, got {type(data).__name__}")
    return data


def _row(env: str, window: str, snap: Dict[str, Any], note: str) -> str:
    return (
        f"| {env} | {window} | {snap.get('total', '')} | "
        f"{snap.get('t1_label_pct', '')} | {snap.get('t2_embedding_pct', '')} | "
        f"{snap.get('t3_llm_pct', '')} | {snap.get('t3_hits', '')} | "
        f"{snap.get('t3_latency_ms_p50', '')} | {snap.get('t3_latency_ms_p95', '')} | "
        f"{snap.get('t2_boundary_hits', '')} | {snap.get('t2_reject_hits', '')} | "
        f"{note} |"
    )


def _aggregate(snaps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Sum hit counters across replicas; latency percentiles not mergeable → None."""
    keys = (
        "total",
        "t1_hits",
        "t2_hits",
        "t3_hits",
        "t2_boundary_hits",
        "t2_reject_hits",
        "llm_calls_avoided",
        "estimated_token_saved",
        "t3_latency_samples",
    )
    out: Dict[str, Any] = {k: 0 for k in keys}
    for s in snaps:
        for k in keys:
            try:
                out[k] += int(s.get(k) or 0)
            except (TypeError, ValueError):
                pass
    total = int(out["total"]) or 1
    out["t1_label_pct"] = round(100 * out["t1_hits"] / total, 1) if out["total"] else 0.0
    out["t2_embedding_pct"] = round(100 * out["t2_hits"] / total, 1) if out["total"] else 0.0
    out["t3_llm_pct"] = round(100 * out["t3_hits"] / total, 1) if out["total"] else 0.0
    out["t3_latency_ms_p50"] = None
    out["t3_latency_ms_p95"] = None
    out["scope"] = "multi-process-sum"
    out["honesty"] = (
        HONESTY + "; latency p50/p95 not merged across replicas — use per-replica rows"
    )
    out["replicas"] = len(snaps)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    """main。

    Args:
        argv: argv 参数。
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--base",
        action="append",
        dest="bases",
        help="Core base URL (repeatable). Default: $CORE_BASE or http://127.0.0.1:8002",
    )
    ap.add_argument("--path", default=DEFAULT_PATH)
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--env", default="dev", help="Environment label for the table row")
    ap.add_argument(
        "--window",
        default="",
        help="Observation window label (e.g. 2026-11-01..2026-11-08)",
    )
    ap.add_argument(
        "--jsonl",
        type=Path,
        help="Append one JSON object per successful scrape (and aggregate if multi)",
    )
    ap.add_argument(
        "--aggregate",
        action="store_true",
        help="With multiple --base, also print a summed markdown row (latency cleared)",
    )
    ap.add_argument("--json", action="store_true", help="Print raw JSON snapshots to stdout")
    args = ap.parse_args(argv)

    bases = list(args.bases or [])
    if not bases:
        bases = [os.environ.get("CORE_BASE", "http://127.0.0.1:8002").rstrip("/")]

    window = args.window or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    snaps: List[Dict[str, Any]] = []
    errors: List[str] = []

    print(f"# honesty: {HONESTY}", file=sys.stderr)
    for base in bases:
        url = base.rstrip("/") + args.path
        try:
            snap = _fetch(url, args.timeout)
            snap["_scraped_from"] = url
            snap["_scraped_at"] = datetime.now(timezone.utc).isoformat()
            snaps.append(snap)
            print(f"OK {url} total={snap.get('total')} t3={snap.get('t3_hits')}", file=sys.stderr)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError) as e:
            errors.append(f"{url}: {e}")
            print(f"FAIL {url}: {e}", file=sys.stderr)

    if not snaps:
        print("FAIL: no successful scrapes", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print(
            "Hint: restart/redeploy core after PR #612 so "
            "/diagnostics/domain-router/route-stats exists.",
            file=sys.stderr,
        )
        return 1

    if args.jsonl:
        args.jsonl.parent.mkdir(parents=True, exist_ok=True)
        with args.jsonl.open("a", encoding="utf-8") as fh:
            for s in snaps:
                fh.write(json.dumps(s, ensure_ascii=False) + "\n")
            if args.aggregate and len(snaps) > 1:
                fh.write(json.dumps(_aggregate(snaps), ensure_ascii=False) + "\n")

    if args.json:
        print(json.dumps(snaps if len(snaps) > 1 else snaps[0], ensure_ascii=False, indent=2))
    else:
        print(
            "| 环境 | 窗口 | total | t1% | t2% | t3% | t3_n | T3 p50 ms | T3 p95 ms | "
            "t2_boundary | t2_reject | 备注 |"
        )
        print("|------|------|------|-----|-----|-----|------|-----------|-----------|-------------|-----------|------|")
        for i, s in enumerate(snaps):
            note = f"replica={i+1}/{len(snaps)}; uptime_s={s.get('stats_uptime_s', '')}"
            print(_row(args.env, window, s, note))
        if args.aggregate and len(snaps) > 1:
            print(_row(args.env, window, _aggregate(snaps), "summed hits; latency N/A"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
