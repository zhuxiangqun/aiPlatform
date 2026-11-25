"""评测 / FDE 覆盖率探针（Phase 2 / G2 诚实锁）。

slice-1：仅返回可声明的覆盖度量槽位；缺测时 coverage 为 0 且 ``baseline_missing``。
不宣称 L4、不伪造 ≥90%/≥95%。
"""
from __future__ import annotations

from typing import Any, Dict, Optional


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
            "threshold": 0.90,
            "g2_foundation": True,
            "certified": False,
            "e2_claimed": False,
            "note": "eval coverage not measured; do not claim G2",
        }
    cov = max(0.0, min(1.0, float(m.get("coverage") or 0)))
    return {
        "ok": True,
        "coverage": cov,
        "baseline_missing": False,
        "meets_g2_threshold": cov >= 0.90,
        "threshold": 0.90,
        "g2_foundation": True,
        "certified": False,
        "e2_claimed": False,
    }


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
            "threshold": 0.95,
            "g2_foundation": True,
            "certified": False,
            "e2_claimed": False,
            "note": "fde evidence coverage not measured; do not claim G2",
        }
    cov = max(0.0, min(1.0, float(m.get("coverage") or 0)))
    return {
        "ok": True,
        "coverage": cov,
        "baseline_missing": False,
        "meets_g2_threshold": cov >= 0.95,
        "threshold": 0.95,
        "g2_foundation": True,
        "certified": False,
        "e2_claimed": False,
    }
