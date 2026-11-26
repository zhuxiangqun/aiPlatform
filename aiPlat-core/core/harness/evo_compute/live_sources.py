"""生产加深 D1：活源摘要（Harness 侧；不直导 apps/Platform）。

由 CoreFacade 注入已桥接的 eval report / FDE inventory / canary rollout / baseline。
缺源诚实 ``unavailable`` / ``baseline_missing``；不宣称 Gate/E2。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from core.harness.evo_compute.coverage import (
    EVAL_THRESHOLD,
    FDE_THRESHOLD,
    coverage_ratio_from_inventory,
    measure_eval_coverage_from_capability_report,
    measure_fde_evidence_coverage_from_inventory,
)

# 闭环 L4 关注的四键（与 loops_l4 对齐；governance/knowledge/eval/fde）
_LOOP_KEYS = ("governance", "knowledge", "eval", "fde")


def _honesty() -> Dict[str, Any]:
    return {
        "g3_foundation": True,
        "g3_complete": False,
        "g2_complete": False,
        "certified": False,
        "e2_claimed": False,
        "production_write": False,
    }


def summarize_live_eval_coverage(
    report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """接纳 Facade 桥接的 capability report → 评测覆盖摘要。

    Args:
        report: ``eval.capability_coverage.v1`` 或已测探针回执；None/空 → unavailable。
    """
    if not isinstance(report, dict) or not report:
        return {
            "ok": True,
            "available": False,
            "source": "unavailable",
            "baseline_missing": True,
            "coverage": 0.0,
            "meets_threshold": False,
            "threshold": EVAL_THRESHOLD,
            **_honesty(),
            "note": "eval coverage source unavailable; not measured",
        }
    # 若已是 measure_* 形回执
    if "coverage" in report and "baseline_missing" in report:
        miss = bool(report.get("baseline_missing"))
        cov = float(report.get("coverage") or 0.0)
        return {
            "ok": True,
            "available": not miss,
            "source": "live" if not miss else "unavailable",
            "baseline_missing": miss,
            "coverage": cov,
            "meets_threshold": (not miss) and cov >= EVAL_THRESHOLD,
            "threshold": EVAL_THRESHOLD,
            "detail": report,
            **_honesty(),
            "note": "live eval coverage summary"
            if not miss
            else "eval report present but baseline_missing",
        }
    measured = measure_eval_coverage_from_capability_report(report)
    miss = bool(measured.get("baseline_missing"))
    cov = float(measured.get("coverage") or 0.0)
    return {
        "ok": True,
        "available": not miss,
        "source": "live" if not miss else "unavailable",
        "baseline_missing": miss,
        "coverage": cov,
        "meets_threshold": (not miss) and cov >= EVAL_THRESHOLD,
        "threshold": EVAL_THRESHOLD,
        "detail": measured,
        **_honesty(),
        "note": "live eval coverage from capability report"
        if not miss
        else "capability report unmeasurable",
    }


def summarize_live_fde_coverage(
    inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """库存形 FDE 证据覆盖摘要。

    Args:
        inventory: ``{covered_ids, required_ids}``；缺则 unavailable。
    """
    if not isinstance(inventory, dict) or not inventory:
        return {
            "ok": True,
            "available": False,
            "source": "unavailable",
            "baseline_missing": True,
            "coverage": 0.0,
            "meets_threshold": False,
            "threshold": FDE_THRESHOLD,
            **_honesty(),
            "note": "fde inventory unavailable; not measured",
        }
    measured = measure_fde_evidence_coverage_from_inventory(
        covered_ids=inventory.get("covered_ids"),
        required_ids=inventory.get("required_ids"),
    )
    miss = bool(measured.get("baseline_missing"))
    cov = float(measured.get("coverage") or 0.0)
    return {
        "ok": True,
        "available": not miss,
        "source": "live" if not miss else "unavailable",
        "baseline_missing": miss,
        "coverage": cov,
        "meets_threshold": (not miss) and cov >= FDE_THRESHOLD,
        "threshold": FDE_THRESHOLD,
        "detail": measured,
        "ratio_probe": coverage_ratio_from_inventory(
            covered_ids=inventory.get("covered_ids"),
            required_ids=inventory.get("required_ids"),
        ),
        **_honesty(),
        "note": "live fde coverage from inventory"
        if not miss
        else "fde inventory empty/unmeasurable",
    }


def probe_canary_rollout(
    rollout_rows: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """只读归一化 SkillRouter rollout 探针（不切流、不回滚）。

    Args:
        rollout_rows: Facade 注入的 rollout 行列表；None → unavailable。
    """
    if rollout_rows is None:
        return {
            "ok": True,
            "available": False,
            "source": "unavailable",
            "skill_count": 0,
            "ab_active_count": 0,
            "rows": [],
            "cutover": False,
            **_honesty(),
            "note": "canary rollout probe unavailable; read-only deepen only",
        }
    rows = [dict(r) for r in rollout_rows if isinstance(r, dict)]
    ab = sum(1 for r in rows if r.get("ab_active"))
    return {
        "ok": True,
        "available": True,
        "source": "live",
        "skill_count": len(rows),
        "ab_active_count": ab,
        "rows": rows[:50],
        "cutover": False,
        **_honesty(),
        "note": "read-only canary rollout probe; no traffic cutover",
    }


def levels_from_baseline_loops(
    baseline: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """从闭环基线抽出四闭环 ``measured_level`` 供 L4 报告。

    Args:
        baseline: ``measure_closed_loop_baseline`` 回执。

    Returns:
        ``levels`` / ``measured``；缺测则 measured=false。
    """
    if not isinstance(baseline, dict) or not baseline:
        return {
            "ok": True,
            "available": False,
            "measured": False,
            "levels": {k: 0 for k in _LOOP_KEYS},
            "source": "unavailable",
            **_honesty(),
            "note": "baseline unavailable; loops L4 not measured",
        }
    loops = baseline.get("loops") if isinstance(baseline.get("loops"), dict) else {}
    levels: Dict[str, int] = {}
    any_measured = False
    for k in _LOOP_KEYS:
        loop = loops.get(k) if isinstance(loops.get(k), dict) else {}
        ml = loop.get("measured_level")
        if ml is None:
            levels[k] = 0
            continue
        try:
            lv = int(str(ml).split("-")[0])
        except (TypeError, ValueError):
            lv = 0
        levels[k] = lv
        if lv > 0 and not loop.get("baseline_missing"):
            any_measured = True
    # 四键皆有正等级且无 baseline_missing 才算 measured
    all_ok = True
    for k in _LOOP_KEYS:
        loop = loops.get(k) if isinstance(loops.get(k), dict) else {}
        if loop.get("measured_level") is None or loop.get("baseline_missing"):
            all_ok = False
            break
        if levels.get(k, 0) <= 0:
            all_ok = False
            break
    return {
        "ok": True,
        "available": bool(loops),
        "measured": bool(all_ok),
        "levels": levels,
        "any_partial": any_measured and not all_ok,
        "source": "live" if all_ok else ("partial" if any_measured else "unavailable"),
        "baseline_owner": baseline.get("owner") or "",
        **_honesty(),
        "note": "levels from closed_loop baseline"
        if all_ok
        else "baseline present but loops not fully measured",
    }

