#!/usr/bin/env python3
"""Phase 2 D4 stress: 200× accept_order via Registry.execute → insert_audit.

Measures P95 of execute→audit (excluding human approval; uses _bypass_approval).

Usage:
  PYTHONPATH=aiPlat-core python3 scripts/bench_accept_order_p95.py --count 200
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "aiPlat-core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))


async def _run(count: int, prefix: str, domain_id: str, home: str) -> int:
    if home:
        os.environ["AIPLAT_HOME"] = home
    from core.harness.infrastructure.action_store import ActionStore
    from core.harness.ontology_engine.graph_index import GraphIndex
    from core.harness.ontology_engine.action_registry import AsyncActionRegistry
    from core.harness.ontology_engine.builtin_actions import register_all
    from scripts.seed_lock_service_orders import seed_orders

    GraphIndex._loaded_instances.clear()
    ids = seed_orders(count, prefix, domain_id)

    audit_db = str(Path(home) / "action_audit_bench.db")
    store = ActionStore(db_path=audit_db)
    await store.initialize()

    reg = AsyncActionRegistry(store=store)
    register_all(reg)
    action_id = "customer_action:lock-service:accept_order"
    assert reg.get(action_id) is not None
    assert reg.get("accept_order") is not None  # alias

    latencies_ms: list[float] = []
    failures = 0
    for eid in ids:
        t0 = time.perf_counter()
        result = await reg.execute(
            action_id,
            (domain_id, eid),
            {"assigned_technician": "tech-1", "scheduled_at": "2026-09-15T09:00:00+08:00"},
            actor="bench",
            role="agent",
            _bypass_approval=True,
        )
        dt = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(dt)
        if result.get("status") not in {"executed", "done", "completed", "success", "ok"}:
            failures += 1
            print("FAIL", eid, result)

    latencies_ms.sort()
    p95 = latencies_ms[max(0, int(len(latencies_ms) * 0.95) - 1)]
    mean = statistics.mean(latencies_ms)

    # Count + sample audit completeness (schema embed in params)
    sample_eid = ids[0]
    sample_rows = await store.list_audit(entity_id=sample_eid, domain_id=domain_id, limit=50)
    audits = 0
    for eid in ids:
        rows = await store.list_audit(entity_id=eid, domain_id=domain_id, limit=5)
        audits += len(rows)
    complete = 0
    for r in sample_rows:
        params = r.get("params") or {}
        if isinstance(params, str):
            import json
            try:
                params = json.loads(params)
            except Exception:
                params = {}
        if params.get("schema") == "audit.v1" and params.get("action_namespace") == "customer_action":
            complete += 1
    complete_rate = (complete / max(1, len(sample_rows))) * 100.0

    # Query P95: entity audit list (limit 50)
    query_ms: list[float] = []
    for eid in ids[: min(50, len(ids))]:
        t0 = time.perf_counter()
        await store.list_audit(entity_id=eid, domain_id=domain_id, limit=50)
        query_ms.append((time.perf_counter() - t0) * 1000.0)
    query_ms.sort()
    q_p95 = query_ms[max(0, int(len(query_ms) * 0.95) - 1)] if query_ms else 0.0

    print(f"count={count} failures={failures} audits={audits}")
    print(f"latency_ms mean={mean:.2f} p95={p95:.2f} max={latencies_ms[-1]:.2f}")
    print(f"audit_complete_sample={complete}/{len(sample_rows)} ({complete_rate:.0f}%) query_p95_ms={q_p95:.2f}")
    ok = (
        failures == 0
        and audits == count
        and p95 < 500.0
        and complete_rate >= 100.0
        and q_p95 < 100.0
    )
    print(
        "PASS" if ok else "FAIL",
        f"(D4: fail=0 audits={count} exec_p95<500 query_p95<100 complete=100%)",
    )
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=200)
    p.add_argument("--prefix", default="IO-BENCH")
    p.add_argument("--domain", default="lock-service")
    p.add_argument("--home", default="")
    args = p.parse_args(argv)
    home = args.home or str(Path("/tmp") / f"aiplat_bench_{os.getpid()}")
    Path(home).mkdir(parents=True, exist_ok=True)
    return asyncio.run(_run(args.count, args.prefix, args.domain, home))


if __name__ == "__main__":
    raise SystemExit(main())
