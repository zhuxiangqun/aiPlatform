#!/usr/bin/env python3
"""Seed lock-service InstallOrder entities for Phase 2 vertical slice (D4).

Usage:
  PYTHONPATH=aiPlat-core python3 scripts/seed_lock_service_orders.py --count 200
  PYTHONPATH=aiPlat-core python3 scripts/seed_lock_service_orders.py --count 20 --prefix IO-TEST
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "aiPlat-core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))


def seed_orders(count: int, prefix: str, domain_id: str) -> list[str]:
    from core.harness.ontology_engine.graph_index import GraphIndex

    # Clear cached instances so AIPLAT_HOME takes effect
    GraphIndex._loaded_instances.clear()
    g = GraphIndex(domain_id)
    ids: list[str] = []
    for i in range(1, count + 1):
        eid = f"{prefix}-{i:04d}"
        g.add_entity(eid, f"Install Order {i}", "安装工单", source_doc_id="phase2-seed")
        g.add_entity_property(eid, "state", "pending")
        g.add_entity_property(eid, "site", f"site-{(i % 5) + 1}")
        ids.append(eid)
    g.save()
    return ids


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Seed lock-service InstallOrders")
    p.add_argument("--count", type=int, default=200)
    p.add_argument("--prefix", default="IO-P2")
    p.add_argument("--domain", default="lock-service")
    p.add_argument(
        "--home",
        default="",
        help="Override AIPLAT_HOME (graph DB root)",
    )
    args = p.parse_args(argv)
    if args.home:
        os.environ["AIPLAT_HOME"] = args.home
    ids = seed_orders(args.count, args.prefix, args.domain)
    print(f"seeded {len(ids)} InstallOrder entities in domain={args.domain}")
    print(f"first={ids[0]} last={ids[-1]}")
    print(f"AIPLAT_HOME={os.environ.get('AIPLAT_HOME', '~/.aiplat')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
