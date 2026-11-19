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



def _script_graph_tenant(tenant_id: str = "") -> str:
    """Resolve tenant for script GraphIndex writes (N09 K35).

    Args:
        tenant_id: 显式租户；空则 CoreFacade resolve_graph_tenant，失败回落 default。
    """
    tid = (tenant_id or "").strip()
    if tid:
        return tid
    try:
        from core.api.core_facade import resolve_graph_tenant
        return resolve_graph_tenant()
    except Exception:
        import logging
        logging.getLogger(__name__).debug(
            "script resolve_graph_tenant failed; using default",
            exc_info=True,
        )
        return "default"


def seed_orders(count: int, prefix: str, domain_id: str, *, tenant_id: str = "") -> list[str]:
    """seed_orders。

    Args:
        count: count 参数。
        prefix: prefix 参数。
        domain_id: domain 标识。
        tenant_id: 租户；空则 resolve（N09 K35）。
    """
    from core.harness.ontology_engine.graph_index import GraphIndex

    # Clear cached instances so AIPLAT_HOME takes effect
    GraphIndex._loaded_instances.clear()
    g = GraphIndex(domain_id, tenant_id=_script_graph_tenant(tenant_id))
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
    """main。

    Args:
        argv: argv 参数。
    """
    p = argparse.ArgumentParser(description="Seed lock-service InstallOrders")
    p.add_argument("--count", type=int, default=200)
    p.add_argument("--prefix", default="IO-P2")
    p.add_argument("--domain", default="lock-service")
    p.add_argument(
        "--home",
        default="",
        help="Override AIPLAT_HOME (graph DB root)",
    )
    p.add_argument("--tenant", default="", help="GraphIndex tenant id (N09 K35)")
    args = p.parse_args(argv)
    if args.home:
        os.environ["AIPLAT_HOME"] = args.home
    ids = seed_orders(args.count, args.prefix, args.domain, tenant_id=args.tenant)
    print(f"seeded {len(ids)} InstallOrder entities in domain={args.domain}")
    print(f"first={ids[0]} last={ids[-1]}")
    print(f"AIPLAT_HOME={os.environ.get('AIPLAT_HOME', '~/.aiplat')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
