"""评测 / FDE 覆盖率探针（Phase 2 / G2）。

slice-1：缺测诚实（``baseline_missing``）。
slice-2：库存/报告驱动的**实测**路径（covered/required）；仍不宣称生产 L4。

Harness 不直导 apps；Facade 可将评测报告映射为本模块 inventory/report 形状。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


EVAL_THRESHOLD = 0.90
FDE_THRESHOLD = 0.95


def _ids(values: Optional[Iterable[Any]]) -> List[str]:
    """规范化 ID 列表（去空、保序去重）。"""
    out: List[str] = []
    seen: Set[str] = set()
    for v in values or []:
        s = str(v or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def coverage_ratio_from_inventory(
    *,
    covered_ids: Optional[Sequence[Any]] = None,
    required_ids: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """由库存计算覆盖率（covered ∩ required / |required|）。

    Args:
        covered_ids: 已覆盖项。
        required_ids: 应覆盖全集；空则不可测。

    Returns:
        ``coverage`` / ``baseline_missing`` / 计数；不判定门限。
    """
    required = _ids(required_ids)
    covered = set(_ids(covered_ids))
    if not required:
        return {
            "ok": True,
            "coverage": 0.0,
            "baseline_missing": True,
            "required_count": 0,
            "covered_count": 0,
            "covered_ids": [],
            "missing_ids": [],
            "note": "required_ids empty; coverage not measured",
        }
    hit = [r for r in required if r in covered]
    miss = [r for r in required if r not in covered]
    cov = len(hit) / float(len(required))
    return {
        "ok": True,
        "coverage": round(cov, 6),
        "baseline_missing": False,
        "required_count": len(required),
        "covered_count": len(hit),
        "covered_ids": hit,
        "missing_ids": miss,
        "source": "inventory",
    }


def coverage_ratio_from_capability_report(
    report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """将 ``eval.capability_coverage.v1`` 形报告映射为覆盖率。

    Args:
        report: 须含 ``covered_capabilities`` 与 ``total_in_scope``（或 gaps）。

    Returns:
        与 inventory 同形；缺字段则 ``baseline_missing``。
    """
    r = dict(report or {})
    total = r.get("total_in_scope")
    covered = r.get("covered_capabilities")
    if total is None or covered is None:
        gaps = r.get("gaps")
        if isinstance(gaps, list) and gaps:
            total = len(gaps)
            covered = sum(1 for g in gaps if isinstance(g, dict) and g.get("ok") is True)
        else:
            return {
                "ok": True,
                "coverage": 0.0,
                "baseline_missing": True,
                "required_count": 0,
                "covered_count": 0,
                "note": "capability report missing totals; not measured",
                "source": "capability_report",
            }
    try:
        t = int(total)
        c = int(covered)
    except (TypeError, ValueError):
        return {
            "ok": True,
            "coverage": 0.0,
            "baseline_missing": True,
            "note": "capability report totals not numeric",
            "source": "capability_report",
        }
    if t <= 0:
        return {
            "ok": True,
            "coverage": 0.0,
            "baseline_missing": True,
            "required_count": 0,
            "covered_count": 0,
            "note": "total_in_scope=0; not measured",
            "source": "capability_report",
        }
    c = max(0, min(c, t))
    return {
        "ok": True,
        "coverage": round(c / float(t), 6),
        "baseline_missing": False,
        "required_count": t,
        "covered_count": c,
        "source": "capability_report",
        "subject_kind": r.get("subject_kind"),
        "n_gaps": r.get("n_gaps"),
        "claim_eligible": False,
        "accuracy_claim": False,
    }


def coverage_from_baseline_kpi(
    baseline: Optional[Dict[str, Any]] = None,
    *,
    loop_id: str,
    kpi_key: str,
) -> Dict[str, Any]:
    """从闭环基线 KPI 槽位读取覆盖率。

    Args:
        baseline: ``measure_closed_loop_baseline`` 回执。
        loop_id: 闭环 id（eval/fde/…）。
        kpi_key: KPI 键。

    Returns:
        有数值则实测；否则缺测。
    """
    loops = (baseline or {}).get("loops") or {}
    loop = loops.get(str(loop_id) or "") or {}
    kpi = loop.get("kpi") or {}
    raw = kpi.get(str(kpi_key) or "")
    if raw is None:
        return {
            "ok": True,
            "coverage": 0.0,
            "baseline_missing": True,
            "source": "baseline_kpi",
            "loop_id": loop_id,
            "kpi_key": kpi_key,
            "note": "kpi slot null; not measured",
        }
    try:
        cov = max(0.0, min(1.0, float(raw)))
    except (TypeError, ValueError):
        return {
            "ok": True,
            "coverage": 0.0,
            "baseline_missing": True,
            "source": "baseline_kpi",
            "note": "kpi not numeric",
        }
    return {
        "ok": True,
        "coverage": cov,
        "baseline_missing": False,
        "source": "baseline_kpi",
        "loop_id": loop_id,
        "kpi_key": kpi_key,
    }


def default_g2_eval_inventory_fixture(*, meet_threshold: bool = True) -> Dict[str, List[str]]:
    """评测覆盖夹具（10 能力槽；达标 9/10，未达标 8/10）。

    Args:
        meet_threshold: True→0.9，False→0.8。
    """
    required = [f"cap.{i:02d}" for i in range(1, 11)]
    n = 9 if meet_threshold else 8
    return {"required_ids": required, "covered_ids": required[:n]}


def default_g2_fde_inventory_fixture(*, meet_threshold: bool = True) -> Dict[str, List[str]]:
    """FDE 证据覆盖夹具（20 槽；达标 19/20=0.95，未达标 18/20）。

    Args:
        meet_threshold: True→≥0.95，False→0.9。
    """
    required = [f"evidence.{i:02d}" for i in range(1, 21)]
    n = 19 if meet_threshold else 18
    return {"required_ids": required, "covered_ids": required[:n]}


def measure_eval_coverage(measured: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """评测覆盖率探针。

    Args:
        measured: 可选实测 ``{"coverage": 0.0-1.0, ...}``。

    Returns:
        回执；未提供实测则 ``baseline_missing=true``、coverage=0。
    """
    m = dict(measured or {})
    if "coverage" not in m:
        return {
            "ok": True,
            "coverage": 0.0,
            "baseline_missing": True,
            "meets_g2_threshold": False,
            "threshold": EVAL_THRESHOLD,
            "g2_foundation": True,
            "certified": False,
            "e2_claimed": False,
            "note": "eval coverage not measured; do not claim G2",
        }
    cov = max(0.0, min(1.0, float(m.get("coverage") or 0)))
    out = {
        "ok": True,
        "coverage": cov,
        "baseline_missing": False,
        "meets_g2_threshold": cov >= EVAL_THRESHOLD,
        "threshold": EVAL_THRESHOLD,
        "g2_foundation": True,
        "certified": False,
        "e2_claimed": False,
    }
    for k in (
        "source",
        "required_count",
        "covered_count",
        "covered_ids",
        "missing_ids",
        "subject_kind",
        "n_gaps",
        "loop_id",
        "kpi_key",
    ):
        if k in m:
            out[k] = m[k]
    return out


def measure_fde_evidence_coverage(
    measured: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """FDE 证据覆盖率探针。

    Args:
        measured: 可选实测 ``{"coverage": 0.0-1.0, ...}``。

    Returns:
        回执；未提供实测则缺测诚实上报。
    """
    m = dict(measured or {})
    if "coverage" not in m:
        return {
            "ok": True,
            "coverage": 0.0,
            "baseline_missing": True,
            "meets_g2_threshold": False,
            "threshold": FDE_THRESHOLD,
            "g2_foundation": True,
            "certified": False,
            "e2_claimed": False,
            "note": "fde evidence coverage not measured; do not claim G2",
        }
    cov = max(0.0, min(1.0, float(m.get("coverage") or 0)))
    out = {
        "ok": True,
        "coverage": cov,
        "baseline_missing": False,
        "meets_g2_threshold": cov >= FDE_THRESHOLD,
        "threshold": FDE_THRESHOLD,
        "g2_foundation": True,
        "certified": False,
        "e2_claimed": False,
    }
    for k in (
        "source",
        "required_count",
        "covered_count",
        "covered_ids",
        "missing_ids",
        "loop_id",
        "kpi_key",
    ):
        if k in m:
            out[k] = m[k]
    return out


def measure_eval_coverage_from_inventory(
    *,
    covered_ids: Optional[Sequence[Any]] = None,
    required_ids: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """评测覆盖：库存 → 探针。

    Args:
        covered_ids: 已覆盖。
        required_ids: 应覆盖。
    """
    ratio = coverage_ratio_from_inventory(
        covered_ids=covered_ids, required_ids=required_ids
    )
    if ratio.get("baseline_missing"):
        return measure_eval_coverage(None)
    return measure_eval_coverage(ratio)


def measure_fde_evidence_coverage_from_inventory(
    *,
    covered_ids: Optional[Sequence[Any]] = None,
    required_ids: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """FDE 证据覆盖：库存 → 探针。

    Args:
        covered_ids: 已覆盖证据项。
        required_ids: 应覆盖证据项。
    """
    ratio = coverage_ratio_from_inventory(
        covered_ids=covered_ids, required_ids=required_ids
    )
    if ratio.get("baseline_missing"):
        return measure_fde_evidence_coverage(None)
    return measure_fde_evidence_coverage(ratio)


def measure_eval_coverage_from_capability_report(
    report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """评测覆盖：能力覆盖报告 → 探针。

    Args:
        report: ``eval.capability_coverage.v1`` 形。
    """
    ratio = coverage_ratio_from_capability_report(report)
    if ratio.get("baseline_missing"):
        return measure_eval_coverage(None)
    return measure_eval_coverage(ratio)
