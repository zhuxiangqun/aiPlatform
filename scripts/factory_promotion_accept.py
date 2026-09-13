#!/usr/bin/env python3
"""晋升门验收：写入 hop 样本并调用 evaluate_project_run_through。

用法：
  python3 scripts/factory_promotion_accept.py                 # 默认隔离临时 HOME
  python3 scripts/factory_promotion_accept.py --project-id prj_demo
  python3 scripts/factory_promotion_accept.py --use-home      # 写真实 AIPLAT_HOME
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_module(name: str, rel: str):
    path = _repo_root() / rel
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    # Ensure sibling imports (builder.promotion_gate) resolve when hop_metrics loads them
    plat = str(_repo_root() / "aiPlat-platform")
    if plat not in sys.path:
        sys.path.insert(0, plat)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description="Promotion gate acceptance with hop samples")
    ap.add_argument("--project-id", default="prj_promo_accept")
    ap.add_argument("--use-home", action="store_true", help="Use real AIPLAT_HOME")
    ap.add_argument("--mature", action="store_true", help="Use mature success_rate threshold")
    args = ap.parse_args()

    tmp: Optional[tempfile.TemporaryDirectory] = None
    if not args.use_home:
        tmp = tempfile.TemporaryDirectory(prefix="aiplat_promo_")
        os.environ["AIPLAT_HOME"] = tmp.name
        print(f"AIPLAT_HOME={tmp.name} (isolated)")
    else:
        print(f"AIPLAT_HOME={os.getenv('AIPLAT_HOME', os.path.expanduser('~/.aiplat'))}")

    hm = _load_module("hop_metrics_accept", "aiPlat-platform/builder/hop_metrics.py")
    record_hop = hm.record_hop
    evaluate_project_run_through = hm.evaluate_project_run_through

    pid = args.project_id
    # 20 success + 0 unattributed failures → green at start threshold 0.80
    for i in range(20):
        record_hop(pid, skill="accept_skill", agent="accept_agent", ok=True, mode="single")

    # negative control project: below N
    pid_low = f"{pid}_low"
    for _ in range(5):
        record_hop(pid_low, skill="accept_skill", ok=True)

    green = evaluate_project_run_through(
        pid,
        conformance_green=True,
        real_tests_green=True,
        physical_evidence=True,
        policy_gate_closed=True,
        mature=bool(args.mature),
    )
    low = evaluate_project_run_through(
        pid_low,
        conformance_green=True,
        real_tests_green=True,
        physical_evidence=True,
        policy_gate_closed=True,
    )

    print("=== factory_promotion_accept ===")
    print(f"green project={pid} ok={green.get('ok')} blockers={green.get('blockers')}")
    print(f"  hops={green.get('hops')}")
    print(f"low project={pid_low} ok={low.get('ok')} blockers={low.get('blockers')}")

    if tmp is not None:
        tmp.cleanup()

    if green.get("ok") is not True:
        print("FAIL: expected green project to pass run-through")
        return 1
    if low.get("ok") is not False:
        print("FAIL: expected low-N project to be blocked")
        return 1
    print("PASS: promotion gate accepts N≥20 attributed hops; rejects low N")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
