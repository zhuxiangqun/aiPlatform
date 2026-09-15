#!/usr/bin/env python3
"""Report Ontology Completeness Score (OCS) per domain.

Usage:
  PYTHONPATH=aiPlat-core python3 scripts/report_ontology_completeness.py
  PYTHONPATH=aiPlat-core python3 scripts/report_ontology_completeness.py --domain lock-service
  PYTHONPATH=aiPlat-core python3 scripts/report_ontology_completeness.py --min-ocs 70 --domain lock-service
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "aiPlat-core"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Ontology Completeness Score report")
    parser.add_argument("--domain", default="", help="Single domain_id")
    parser.add_argument(
        "--min-ocs",
        type=float,
        default=0.0,
        help="Exit 1 if named --domain scores below this (CI ratchet)",
    )
    args = parser.parse_args()

    from core.harness.knowledge.ontology_completeness import (
        compute_all_ocs,
        compute_domain_ocs,
    )

    if args.domain:
        rows = [compute_domain_ocs(args.domain)]
    else:
        rows = compute_all_ocs()

    print(f"{'domain':28} {'ocs':>6} {'lvl':10} C1   C2   C3   C4   C5   C6")
    print("-" * 78)
    for r in sorted(rows, key=lambda x: -x.get("ocs", 0)):
        d = r.get("dimensions") or {}
        print(
            f"{r['domain_id']:28} {r.get('ocs', 0):6.1f} {r.get('level', ''):10}"
            f" {d.get('C1', 0):4.0f} {d.get('C2', 0):4.0f} {d.get('C3', 0):4.0f}"
            f" {d.get('C4', 0):4.0f} {d.get('C5', 0):4.0f} {d.get('C6', 0):4.0f}"
        )

    if args.domain and args.min_ocs > 0:
        ocs = rows[0].get("ocs") or 0
        if ocs < args.min_ocs:
            print(f"FAIL: {args.domain} OCS={ocs} < min={args.min_ocs}")
            return 1
        print(f"PASS: {args.domain} OCS={ocs} >= {args.min_ocs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
