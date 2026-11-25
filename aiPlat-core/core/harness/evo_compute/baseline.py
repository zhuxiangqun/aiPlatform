"""闭环成熟度 KPI 基线落盘（成熟度模型 §3 / §7）。

工作假设 ≠ 已测；无测量值时 ``baseline_missing=true``，禁止宣称升级。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# 五闭环工作假设（与成熟度文档对齐；非已测）
_HYPOTHESIS: Dict[str, Any] = {
    "execution": {"hypothesis_level": 4, "label": "执行闭环"},
    "eval": {"hypothesis_level": 3, "label": "评测闭环"},
    "fde": {"hypothesis_level": 3, "label": "FDE 交付闭环"},
    "knowledge": {"hypothesis_level": "2-3", "label": "知识闭环"},
    "governance": {"hypothesis_level": 2, "label": "治理/自演进闭环"},
}

# 最小 KPI 键（用于记录槽位；实测值由调用方注入）
_KPI_SLOTS: Dict[str, List[str]] = {
    "execution": [
        "receipt_coverage",
        "policy_gate_coverage",
        "failure_recovery_rate",
        "feedback_reflow_rate",
        "human_gate_misuse_rate",
    ],
    "eval": [
        "capability_eval_coverage",
        "gate_automation_rate",
        "failure_regression_rate",
        "evidence_completeness",
        "auto_repair_rate",
    ],
    "fde": [
        "delivery_evidence_coverage",
        "feedback_structured_rate",
        "template_reuse_rate",
        "cross_project_deposit_rate",
        "signoff_close_rate",
    ],
    "knowledge": [
        "source_owner_coverage",
        "evidence_coverage",
        "conflict_resolution_rate",
        "error_rollback_days",
        "feedback_fix_rate",
    ],
    "governance": [
        "issue_discovery_coverage",
        "auto_triage_rate",
        "low_risk_auto_fix_rate",
        "mttr_days",
        "regression_rate",
    ],
}


def _baseline_dir() -> Path:
    """基线落盘目录；不可写时回退临时目录。"""
    import tempfile

    root = os.environ.get("AIPLAT_HOME") or os.path.expanduser("~/.aiplat")
    p = Path(root) / "evo_compute" / "baselines"
    try:
        p.mkdir(parents=True, exist_ok=True)
        return p
    except OSError:
        p = Path(tempfile.gettempdir()) / "aiplat_evo_compute" / "baselines"
        p.mkdir(parents=True, exist_ok=True)
        return p


def measure_closed_loop_baseline(
    *,
    measured: Optional[Dict[str, Dict[str, Any]]] = None,
    owner: str = "",
    persist: bool = True,
    as_of: Optional[str] = None,
) -> Dict[str, Any]:
    """生成五闭环基线包：假设等级 + KPI 槽位 + 可选实测。

    Args:
        measured: ``{loop_id: {kpi_key: value, ...}}``；缺测槽位保持 null。
        owner: 基线 owner（G0 要求明确）。
        persist: 是否落盘。
        as_of: 测量日期标记。

    Returns:
        基线回执；``upgrade_claimed`` 恒 false；缺测则 ``baseline_missing``。
    """
    own = str(owner or "").strip()
    measured = measured or {}
    loops: Dict[str, Any] = {}
    missing_any = False
    for loop_id, meta in _HYPOTHESIS.items():
        slots = {}
        loop_measured = measured.get(loop_id) or {}
        for key in _KPI_SLOTS[loop_id]:
            if key in loop_measured and loop_measured[key] is not None:
                slots[key] = loop_measured[key]
            else:
                slots[key] = None
                missing_any = True
        measured_level = loop_measured.get("measured_level")
        loops[loop_id] = {
            "label": meta["label"],
            "hypothesis_level": meta["hypothesis_level"],
            "measured_level": measured_level,
            "kpi": slots,
            "baseline_missing": measured_level is None or any(v is None for v in slots.values()),
        }
        if loops[loop_id]["baseline_missing"]:
            missing_any = True

    # 整体：仅当五闭环都有 measured_level 时取 min（整数部分）；否则标记未测
    levels = []
    for loop in loops.values():
        ml = loop.get("measured_level")
        if ml is None:
            continue
        try:
            levels.append(int(str(ml).split("-")[0]))
        except ValueError:
            continue
    overall_measured = min(levels) if len(levels) == 5 else None

    out: Dict[str, Any] = {
        "ok": bool(own),
        "error": "" if own else "owner_required",
        "owner": own,
        "as_of": as_of or time.strftime("%Y-%m-%d"),
        "schema": "aiplat.closed_loop_baseline.v1",
        "loops": loops,
        "overall_hypothesis": "≈L3 (min of hypotheses; unverified)",
        "overall_measured_level": overall_measured,
        "baseline_missing": missing_any or overall_measured is None,
        "upgrade_claimed": False,
        "certified": False,
        "g0_foundation": True,
        "aggregation": "min_of_five_loops",
        "note": "hypothesis_level is not a measured KPI; do not claim upgrade without baseline",
    }
    if out["ok"] and persist:
        path = _baseline_dir() / f"baseline_{out['as_of'].replace('-', '')}.json"
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        out["persist_path"] = str(path)
    return out


def run_closed_loop_baseline_suite() -> Dict[str, Any]:
    """基线套件：owner 必填、缺测诚实、禁止升级宣称。"""
    cases = []

    # owner 缺失失败
    bad = measure_closed_loop_baseline(owner="", persist=False)
    cases.append(
        {
            "id": "baseline_owner_required",
            "pass": bad.get("ok") is False and bad.get("error") == "owner_required",
        }
    )

    # 空测：baseline_missing + upgrade_claimed false
    empty = measure_closed_loop_baseline(owner="platform-oncall", persist=False)
    cases.append(
        {
            "id": "baseline_missing_honesty",
            "pass": bool(empty.get("baseline_missing"))
            and empty.get("upgrade_claimed") is False
            and empty.get("ok") is True,
        }
    )

    # 部分注入仍 missing
    partial = measure_closed_loop_baseline(
        owner="platform-oncall",
        measured={"execution": {"receipt_coverage": 0.9}},
        persist=False,
    )
    cases.append(
        {
            "id": "baseline_partial_still_missing",
            "pass": bool(partial.get("baseline_missing"))
            and partial["loops"]["execution"]["kpi"]["receipt_coverage"] == 0.9,
        }
    )

    passed = sum(1 for c in cases if c["pass"])
    return {
        "ok": passed == len(cases),
        "passed": passed,
        "total": len(cases),
        "cases": cases,
        "certified": False,
        "g0_foundation": True,
    }


def evaluate_closed_loop_baseline_gate(suite: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """基线门槛门。

    Args:
        suite: ``run_closed_loop_baseline_suite`` 回执。
    """
    s = suite or run_closed_loop_baseline_suite()
    ok = bool(s.get("ok"))
    return {
        "ok": ok,
        "passed": ok,
        "certified": False,
        "upgrade_claimed": False,
        "g0_foundation": True,
        "suite": s,
    }
