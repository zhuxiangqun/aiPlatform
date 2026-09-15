#!/usr/bin/env python3
"""Report domain YAML axioms load status (ONTOLOGY_RUNTIME_AUTHORITY P1).

Usage:
  PYTHONPATH=aiPlat-core python3 scripts/report_domain_axioms.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "aiPlat-core"))


def main() -> int:
    from core.harness.knowledge.ontology_loader import list_domain_files, load_ontology_from_yaml

    home = Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat"))
    onto_dir = home / "ontologies"
    print(f"ontologies_dir={onto_dir}")
    print(f"{'domain':32} {'axioms':>6} {'classes':>7} {'loaded':>6}")
    print("-" * 56)

    total_ax = 0
    with_ax = 0
    for stem in list_domain_files(str(home)):
        path = onto_dir / f"{stem}.yaml"
        try:
            dom = load_ontology_from_yaml(str(path))
            n_ax = len(dom.axioms or [])
            n_cls = len(dom.classes or [])
            total_ax += n_ax
            if n_ax:
                with_ax += 1
            print(f"{stem:32} {n_ax:6d} {n_cls:7d} {'yes':>6}")
        except Exception as e:
            print(f"{stem:32} {'ERR':>6} {str(e)[:40]}")

    print("-" * 56)
    print(f"domains_with_axioms={with_ax} total_axioms_loaded={total_ax}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
