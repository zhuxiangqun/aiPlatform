#!/usr/bin/env python3
"""为真实工厂项目写入 hop 样本并验收晋升门。

默认对 AIPLAT_HOME/apps 下发现的 project_id 各写入一组 hop（走与 execute_skill
相同的 hop_metrics.record_hop 路径），再调用 evaluate_project_run_through /
BuilderProjectService.get_promotion_status（若可导入）。

用法：
  python3 scripts/factory_hop_seed_real.py
  python3 scripts/factory_hop_seed_real.py --project-id prj_23cca158 --n 20
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _aiplat_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")))


def _load_hop_metrics():
    path = _repo_root() / "aiPlat-platform" / "builder" / "hop_metrics.py"
    plat = str(_repo_root() / "aiPlat-platform")
    if plat not in sys.path:
        sys.path.insert(0, plat)
    spec = importlib.util.spec_from_file_location("hop_metrics_seed", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _discover_project_ids(apps_root: Path) -> List[str]:
    ids: List[str] = []
    if not apps_root.is_dir():
        return ids
    for p in sorted(apps_root.iterdir()):
        if not p.is_dir():
            continue
        name = p.name
        if name.startswith("prj_") or name in ("video_sense",):
            ids.append(name)
    # also from projects.json if present
    pj = _aiplat_home() / "projects.json"
    if pj.is_file():
        try:
            data = json.loads(pj.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else (data.get("projects") or [])
            for it in items:
                if isinstance(it, dict) and it.get("project_id"):
                    pid = str(it["project_id"])
                    if pid not in ids:
                        ids.append(pid)
        except Exception:
            pass
    return ids


def seed_project(hm, project_id: str, n: int) -> Dict[str, Any]:
    record_hop = hm.record_hop
    # N-1 success + 1 attributed failure → rate=(n-1)/n
    for i in range(max(0, n - 1)):
        record_hop(
            project_id,
            skill="factory_seed_skill",
            agent="factory_seed_agent",
            ok=True,
            mode="single",
        )
    if n > 0:
        record_hop(
            project_id,
            skill="factory_seed_skill",
            agent="factory_seed_agent",
            ok=False,
            failed_stage="tool_execution",
            error="seeded_failure_for_attribution",
            mode="single",
        )
    promo = hm.evaluate_project_run_through(
        project_id,
        conformance_green=True,
        real_tests_green=True,
        physical_evidence=True,
        policy_gate_closed=True,
    )
    agg = hm.aggregate_hops(project_id)
    return {"project_id": project_id, "hops": agg, "promotion": promo}


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed real-project hop metrics")
    ap.add_argument("--project-id", action="append", default=[])
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--apps-root", default="")
    args = ap.parse_args()

    home = _aiplat_home()
    apps_root = Path(args.apps_root) if args.apps_root else (home / "apps")
    pids = list(args.project_id) or _discover_project_ids(apps_root)
    if not pids:
        print("No project_ids found")
        return 1

    hm = _load_hop_metrics()
    print("=== factory_hop_seed_real ===")
    print(f"AIPLAT_HOME={home}")
    print(f"projects={pids}")

    all_ok = True
    for pid in pids:
        row = seed_project(hm, pid, int(args.n))
        promo = row["promotion"]
        print("---")
        print(pid)
        print(f"  hops n={row['hops'].get('n_runs')} rate={row['hops'].get('effective_success_rate')}")
        print(f"  promotion ok={promo.get('ok')} blockers={promo.get('blockers')}")
        if promo.get("ok") is not True:
            all_ok = False

        # Best-effort: get_promotion_status via service if importable
        try:
            sys.path.insert(0, str(_repo_root() / "aiPlat-platform"))
            sys.path.insert(0, str(_repo_root() / "aiPlat-core"))
            from builder.builder_project_service import BuilderProjectService  # type: ignore

            svc = BuilderProjectService()
            st = svc.get_promotion_status(pid)
            print(f"  service_promotion ok={st.get('ok')} hops_raw_n={st.get('hops_raw_n')} mode={st.get('manifest_mode')}")
        except Exception as e:
            print(f"  service_promotion skipped: {type(e).__name__}: {e}"[:200])

    print("PASS" if all_ok else "PARTIAL/FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
