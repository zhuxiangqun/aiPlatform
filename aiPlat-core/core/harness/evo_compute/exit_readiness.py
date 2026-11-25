"""G0 Phase 0 出口就绪检查（诚实锁）。

条件：基线落盘能力 + 三试点登记 + 预算已批准 + 安全边界已签字 + 至少一次回放。
本模块不自动批准预算/签字；缺任一项则 phase0_complete=false。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from core.harness.evo_compute.budget import get_budget_policy
from core.harness.evo_compute.genome_registry import get_genome
from core.harness.evo_compute.pilots import PILOT_GENOME_IDS
from core.harness.evo_compute.safety import get_safety_boundary


def evaluate_g0_exit_readiness(
    *,
    replay_ok: Optional[bool] = None,
    baseline_ok: bool = True,
) -> Dict[str, Any]:
    """评估 Phase 0 / G0 出口条件是否齐备。

    Args:
        replay_ok: 调用方声明是否已完成至少一次离线回放；None 视为未完成。
        baseline_ok: 基线落盘能力是否可用（slice-1 已具备）。

    Returns:
        回执；仅当全部条件真时 ``phase0_complete`` 可为 True；
        certified/e2 恒 false。
    """
    pilots_ok = all(bool(get_genome(gid).get("ok")) for gid in PILOT_GENOME_IDS)
    budget = get_budget_policy()
    budget_ok = bool(budget.get("approved"))
    safety = get_safety_boundary()
    safety_ok = bool(safety.get("signed"))
    replay_done = bool(replay_ok)

    checks = {
        "baseline_ok": bool(baseline_ok),
        "pilots_determined": pilots_ok,
        "budget_approved": budget_ok,
        "safety_signed": safety_ok,
        "replay_done": replay_done,
    }
    all_ok = all(checks.values())
    return {
        "ok": True,
        "ready": all_ok,
        "checks": checks,
        "missing": [k for k, v in checks.items() if not v],
        "pilot_genome_ids": list(PILOT_GENOME_IDS),
        "phase0_complete": all_ok,
        "g0_foundation": True,
        "certified": False,
        "e2_claimed": False,
        "note": (
            "G0 exit only when budget+safety human-signed and pilots+replay done; "
            "never auto-approve"
        ),
    }


def evaluate_g1_exit_readiness(
    *,
    de_es_ok: bool = False,
    lineage_rate: float = 0.0,
    reproducible: bool = False,
    hard_constraint_ok: bool = False,
    holdout_significant: bool = False,
    drill_ok: bool = False,
) -> Dict[str, Any]:
    """评估 Phase 1 / G1 出口条件是否齐备。

    Args:
        de_es_ok: DE/ES 离线循环是否成功。
        lineage_rate: 血缘完整率（须 ≥1.0）。
        reproducible: 可复现检查是否通过。
        hard_constraint_ok: 硬约束零回归。
        holdout_significant: holdout 上预注册显著提升。
        drill_ok: Human Gate / Canary / 回滚演练通过。

    Returns:
        回执；全部满足时 ``g1_complete`` 可为 True；certified/e2 恒 false。
    """
    checks = {
        "de_es_ok": bool(de_es_ok),
        "lineage_complete": float(lineage_rate) >= 1.0,
        "reproducible": bool(reproducible),
        "hard_constraint_ok": bool(hard_constraint_ok),
        "holdout_significant": bool(holdout_significant),
        "drill_ok": bool(drill_ok),
    }
    all_ok = all(checks.values())
    return {
        "ok": True,
        "ready": all_ok,
        "checks": checks,
        "missing": [k for k, v in checks.items() if not v],
        "g1_complete": all_ok,
        "g1_foundation": True,
        "certified": False,
        "e2_claimed": False,
        "note": "G1 exit; surrogate holdout allowed for slice-1; not E2/certified",
    }


def evaluate_g2_exit_readiness(
    *,
    ga_ok: bool = False,
    safety_regression_free: bool = False,
    eval_coverage_ok: bool = False,
    fde_coverage_ok: bool = False,
) -> Dict[str, Any]:
    """评估 Phase 2 / G2 出口条件是否齐备。

    Args:
        ga_ok: 离散 GA 离线循环是否成功。
        safety_regression_free: GA 试点无安全回归。
        eval_coverage_ok: 评测覆盖 ≥90%（须实测，不可缺测冒充）。
        fde_coverage_ok: FDE 证据覆盖 ≥95%（须实测）。

    Returns:
        回执；全部满足时 ``g2_complete`` 可为 True；certified/e2 恒 false。
    """
    checks = {
        "ga_ok": bool(ga_ok),
        "safety_regression_free": bool(safety_regression_free),
        "eval_coverage_ok": bool(eval_coverage_ok),
        "fde_coverage_ok": bool(fde_coverage_ok),
    }
    all_ok = all(checks.values())
    return {
        "ok": True,
        "ready": all_ok,
        "checks": checks,
        "missing": [k for k, v in checks.items() if not v],
        "g2_complete": all_ok,
        "g2_foundation": True,
        "certified": False,
        "e2_claimed": False,
        "note": "G2 exit requires measured eval/FDE coverage; suite green ≠ claim",
    }
