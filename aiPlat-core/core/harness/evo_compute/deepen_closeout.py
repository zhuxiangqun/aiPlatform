"""生产加深 D5：D1–D4 + PSO 工程轨收口（≠ Gate / E2 / certified）。

汇总各加深切片套件绿，置 ``track_engineering_complete``；
``g*_complete`` / ``certified`` / ``e2_claimed`` / ``production_write`` 恒 false。
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def collect_production_deepen_track_closeout(
    *,
    d1: Optional[Dict[str, Any]] = None,
    d2: Optional[Dict[str, Any]] = None,
    d3: Optional[Dict[str, Any]] = None,
    d4: Optional[Dict[str, Any]] = None,
    pso: Optional[Dict[str, Any]] = None,
    run_suites: bool = True,
) -> Dict[str, Any]:
    """组装生产加深轨收口包。

    Args:
        d1: 预跑 D1 suite；缺省且 ``run_suites`` 时现场跑。
        d2: 预跑 D2 suite。
        d3: 预跑 D3 suite。
        d4: 预跑 D4 suite。
        pso: 预跑 PSO suite。
        run_suites: 缺预跑回执时是否执行各 suite。
    """
    from core.harness.evo_compute.suite import (
        run_evo_compute_production_deepen_slice1_suite,
        run_evo_compute_production_deepen_slice2_suite,
        run_evo_compute_production_deepen_slice3_suite,
        run_evo_compute_production_deepen_slice4_suite,
        run_evo_compute_pso_baseline_suite,
    )

    slices: Dict[str, Dict[str, Any]] = {}
    runners = {
        "d1": (d1, run_evo_compute_production_deepen_slice1_suite),
        "d2": (d2, run_evo_compute_production_deepen_slice2_suite),
        "d3": (d3, run_evo_compute_production_deepen_slice3_suite),
        "d4": (d4, run_evo_compute_production_deepen_slice4_suite),
        "pso": (pso, run_evo_compute_pso_baseline_suite),
    }
    missing: list[str] = []
    for key, (pre, runner) in runners.items():
        if isinstance(pre, dict):
            slices[key] = pre
        elif run_suites:
            slices[key] = runner()
        else:
            missing.append(key)
            slices[key] = {"ok": False, "passed": 0, "total": -1, "slice": key}

    claim_flags = (
        "g1_complete",
        "g2_complete",
        "g3_complete",
        "certified",
        "e2_claimed",
        "production_write",
        "production_traffic",
    )
    per: Dict[str, bool] = {}
    for key, s in slices.items():
        suite_green = bool(s.get("ok")) and int(s.get("passed") or 0) == int(
            s.get("total") or -1
        )
        # 诚实：任一回执若误带 Gate 宣称，收口仍拒
        leak = any(bool(s.get(flag)) for flag in claim_flags)
        if leak:
            missing.append(f"{key}:gate_claim_leak")
        per[key] = bool(suite_green and not leak)

    track_ok = all(per.values()) and not any(
        m for m in missing if ":gate_claim_leak" not in m
    )

    return {
        "schema": "aiplat.evo.production_deepen.track_closeout.v0",
        "slice": "production-deepen-d5",
        "slices": {
            k: {"ok": per[k], "suite_slice": (slices[k].get("slice") or k)} for k in per
        },
        "slice_detail": slices,
        "track_engineering_complete": bool(track_ok),
        "missing": missing,
        "g1_foundation": True,
        "g1_complete": False,
        "g2_complete": False,
        "g3_complete": False,
        "certified": False,
        "e2_claimed": False,
        "production_write": False,
        "production_traffic": False,
        "honesty": (
            "track_engineering_complete means D1–D4+PSO suites green only; "
            "≠ g*_complete / certified / e2 / production traffic"
        ),
    }


def evaluate_production_deepen_track_closeout(
    pack: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """评估 D5 收口就绪；Gate 宣称恒 false。

    Args:
        pack: ``collect_production_deepen_track_closeout`` 回执。
    """
    p = (
        dict(pack)
        if isinstance(pack, dict)
        else collect_production_deepen_track_closeout()
    )
    ok = bool(p.get("track_engineering_complete"))
    return {
        "ok": ok,
        "ready": ok,
        "track_engineering_complete": ok,
        "g1_foundation": True,
        "g1_complete": False,
        "g2_complete": False,
        "g3_complete": False,
        "certified": False,
        "e2_claimed": False,
        "production_write": False,
        "production_traffic": False,
        "pack": p,
        "honesty": "ready≠Gate; D5 closeout ≠ production authorize",
    }
