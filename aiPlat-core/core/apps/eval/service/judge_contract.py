"""Judge 输出契约（评测标准附录 F / Extended E07）。

强制 ``judge_id`` + ``calibration_ref`` 显式字段；``calibration_ref`` 可空，
但缺键则不合规。未校准 Judge MUST NOT 单独满足 accuracy gate。
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


def normalize_judge_report(
    raw: Optional[Mapping[str, Any]] = None,
    *,
    default_judge_id: str = "",
) -> Dict[str, Any]:
    """归一化 Judge 报告字段（附录 F）。

    Args:
        raw: 原始 judge 输出。
        default_judge_id: 缺省 judge_id（仅当原值为空时填入）。

    Returns:
        含 ``judge_id`` / ``calibration_ref`` / ``calibrated`` / ``accuracy_gate_eligible``。
    """
    src = dict(raw or {})
    judge_id = str(src.get("judge_id") or default_judge_id or "").strip()
    # calibration_ref 必须显式出现；允许 null/"" 表示未校准
    if "calibration_ref" in src:
        calibration_ref = src.get("calibration_ref")
        if calibration_ref is not None:
            calibration_ref = str(calibration_ref).strip() or None
    else:
        # 从常见嵌套位置投影，否则显式 None
        cal = src.get("calibration") if isinstance(src.get("calibration"), Mapping) else {}
        metrics = src.get("metrics") if isinstance(src.get("metrics"), Mapping) else {}
        calibration_ref = (
            src.get("report_id")
            or (cal or {}).get("report_id")
            or (metrics or {}).get("report_id")
        )
        if calibration_ref is not None:
            calibration_ref = str(calibration_ref).strip() or None

    calibrated = bool(calibration_ref) and bool(src.get("calibrated", True if calibration_ref else False))
    # 附录 F：calibration_ref 空 → 不可单独满足 accuracy gate
    accuracy_gate_eligible = bool(judge_id) and bool(calibration_ref) and calibrated

    out = dict(src)
    out["judge_id"] = judge_id
    out["calibration_ref"] = calibration_ref
    out["calibrated"] = calibrated
    out["accuracy_gate_eligible"] = accuracy_gate_eligible
    out.setdefault("accuracy_claim", False)
    out["honesty"] = (
        "normalize_judge_report: empty calibration_ref ⇒ not accuracy-gate eligible (E07)"
    )
    return out
