#!/usr/bin/env python3
"""Backfill source_fingerprint for code_graph / cap_graph SQLite caches.

Fixes evaluate_freshness stuck on missing_fingerprint_meta (legacy DBs)
without requiring a full rebuild when node data is already present.

Runtime also backfills on zero-diff cache hit:
  capability_graph.build_capability_graph / code_graph.build_graph
(this CLI is the ops/offline equivalent).

Usage:
  PYTHONPATH=aiPlat-core python3 scripts/backfill_graph_fingerprints.py
  AIPLAT_HOME=/path/to/home PYTHONPATH=aiPlat-core python3 scripts/backfill_graph_fingerprints.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "aiPlat-core"))


def _report(label: str, mod) -> dict:
    has = mod.has_cache()
    info = mod.get_cache_info() if has else {}
    fresh = mod.evaluate_freshness() if has else {"stale": None, "reason": "no_cache"}
    n = info.get("files_indexed") or info.get("nodes")
    print(
        f"[{label}] has_cache={has} n={n} stale={fresh.get('stale')} "
        f"reason={fresh.get('reason')} fp={(fresh.get('stored') or '')[:56]}"
    )
    return fresh


def main() -> int:
    from core.harness.knowledge import code_graph_persist as cgp
    from core.harness.knowledge import cap_graph_persist as cap

    print("=== BEFORE ===")
    _report("code_graph", cgp)
    _report("cap_graph", cap)

    if cgp.has_cache() and cgp.evaluate_freshness().get("reason") == "missing_fingerprint_meta":
        from pathlib import Path as P

        nodes, edges = cgp.load_nodes(), cgp.load_edges()
        root = cgp.get_cached_repo_root()
        cgp.save_graph(nodes, edges, P(root) if root else None)
        print(f"code_graph: backfilled fingerprint (nodes={len(nodes)})")

    if cap.has_cache() and cap.evaluate_freshness().get("reason") == "missing_fingerprint_meta":
        nodes, edges = cap.load_nodes(), cap.load_edges()
        cap.save_graph(nodes, edges)
        print(f"cap_graph: backfilled fingerprint (nodes={len(nodes)})")

    # Also exercise capability_graph read-hit backfill path
    try:
        import core.harness.knowledge.capability_graph as cg

        cg._CAP_CACHE = None
        cg._CAP_CACHE_TS = 0
        from core.harness.knowledge.capability_graph import build_capability_graph

        build_capability_graph()
    except Exception as e:
        print(f"capability_graph rebuild note: {e}")

    print("=== AFTER ===")
    import importlib

    importlib.reload(cgp)
    importlib.reload(cap)
    from core.harness.knowledge import code_graph_persist as cgp2
    from core.harness.knowledge import cap_graph_persist as cap2

    fc = _report("code_graph", cgp2)
    fa = _report("cap_graph", cap2)
    ok = fc.get("stale") is False and (
        fa.get("stale") is False or fa.get("reason") == "no_cache"
    )
    # If cap has cache it must be fresh
    if cap2.has_cache() and fa.get("stale") is not False:
        ok = False
    print("RESULT:", "OK" if ok else "STILL STALE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
