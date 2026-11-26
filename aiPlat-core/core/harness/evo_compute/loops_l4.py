"""闭环 L4 评估报告（Phase 3 / G3）。

按成熟度对治理/知识/评测/FDE 闭环给出已测等级或差距清单 + owner 缓释。
非目标：不写生产、不伪造 L4 实测；夹具/缓释 ≠ 生产 L4 认证。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

_LOOP_KEYS = ("governance", "knowledge", "eval", "fde")


def default_loops_l4_levels_fixture() -> Dict[str, int]:
    """夹具：四闭环均达 L4（仅离线演示）。"""
    return {"governance": 4, "knowledge": 4, "eval": 4, "fde": 4}


def default_loops_gap_fixture() -> Dict[str, int]:
    """夹具：存在差距（需缓释才过）。"""
    return {"governance": 3, "knowledge": 4, "eval": 2, "fde": 3}


def build_loops_l4_assessment_report(
    *,
    levels: Optional[Dict[str, Any]] = None,
    target_level: int = 4,
    waiver_owner: str = "",
    waiver_signed: bool = False,
    waiver_gap_list: Optional[Sequence[str]] = None,
    measured: bool = False,
) -> Dict[str, Any]:
    """构建闭环 L4 评估报告。

    Args:
        levels: 各闭环已测等级（1–4）。
        target_level: 目标等级（默认 4）。
        waiver_owner: 缓释 owner。
        waiver_signed: owner 是否签字。
        waiver_gap_list: 差距清单。
        measured: 是否真实测量（夹具须 false）。

    Returns:
        报告；``loops_l4_or_waiver`` 在达标或有效缓释时为 True；
        ``g3_complete``/``certified`` 恒 false。
    """
    tgt = max(1, int(target_level))
    raw = dict(levels or default_loops_l4_levels_fixture())
    normalized: Dict[str, int] = {}
    gaps: List[str] = []
    for k in _LOOP_KEYS:
        try:
            lv = int(raw.get(k, 0))
        except (TypeError, ValueError):
            lv = 0
        normalized[k] = lv
        if lv < tgt:
            gaps.append(f"{k}:L{lv}<L{tgt}")

    all_at_target = len(gaps) == 0
    owner = str(waiver_owner or "").strip()
    gap_list = [str(x) for x in (waiver_gap_list or gaps)]
    waiver_ok = (
        (not all_at_target)
        and bool(waiver_signed)
        and bool(owner)
        and len(gap_list) > 0
    )
    loops_ok = all_at_target or waiver_ok

    return {
        "ok": True,
        "levels": normalized,
        "target_level": tgt,
        "gaps": gaps,
        "all_at_target": all_at_target,
        "waiver": {
            "owner": owner,
            "signed": bool(waiver_signed),
            "gap_list": gap_list,
            "valid": waiver_ok,
        },
        "loops_l4_or_waiver": loops_ok,
        "measured": bool(measured),
        "g3_foundation": True,
        "g3_complete": False,
        "certified": False,
        "e2_claimed": False,
        "production_write": False,
        "note": "assessment report only; fixture/waiver ≠ production L4 certification"
        if not measured
        else "measured levels reported; still ≠ g3_complete/e2 claim",
    }
