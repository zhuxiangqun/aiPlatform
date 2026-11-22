"""Lv4 误报率门重设计（附录 N N08 deepen）。

职责：
  - 历史样本不足时 **拒绝** 自动闭环（禁止 0 样本 fp_rate=0 假绿）
  - Lv4 允许前要求 ``rollback_action_id``
  - 套件/门槛门：``certified`` / ``n08_full`` 恒 false；``lv4_gate_redesigned=true``

非目标：
  - 不宣称 N08 certified / 全量 Action 已 Lv4
  - 不删除 kill switch / require_approval 既有路径
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SUITE_CASES = (
    "zero_samples_denied",
    "high_fp_denied",
    "missing_rollback_denied",
    "healthy_allowed",
    "honesty_certified_false",
)

# 默认最小样本；可用 AIPLAT_LV4_MIN_SAMPLES 覆盖
_DEFAULT_MIN_SAMPLES = 10


class Lv4FalsePositiveGateError(ValueError):
    """Lv4 误报门契约错误。"""


def lv4_min_samples() -> int:
    """解析 Lv4 最小历史样本量。"""
    raw = (os.environ.get("AIPLAT_LV4_MIN_SAMPLES") or "").strip()
    if not raw:
        return _DEFAULT_MIN_SAMPLES
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_MIN_SAMPLES


def evaluate_lv4_fp_gate(
    *,
    action_id: str,
    total: int,
    false_positives: int,
    rollback_action_id: Optional[str] = None,
    fp_rate_max: float = 0.005,
    min_samples: Optional[int] = None,
) -> Dict[str, Any]:
    """评估 Lv4 自动闭环误报门（重设计 v2）。

    Args:
        action_id: 动作 id。
        total: 历史执行条数。
        false_positives: 误报条数。
        rollback_action_id: 回滚动作 id；缺省拒绝。
        fp_rate_max: 误报率上限。
        min_samples: 最小样本；缺省 ``lv4_min_samples()``。
    """
    aid = (action_id or "").strip()
    if not aid:
        raise Lv4FalsePositiveGateError("action_id_required")
    tot = max(0, int(total))
    fps = max(0, int(false_positives))
    if fps > tot:
        raise Lv4FalsePositiveGateError("false_positives_exceed_total")
    need = int(min_samples) if min_samples is not None else lv4_min_samples()
    need = max(1, need)
    rb = (rollback_action_id or "").strip()

    # 为什么：0 样本不得用 fp_rate=0 假绿放行（重设计核心）
    if tot < need:
        return {
            "action_id": aid,
            "allowed": False,
            "total": tot,
            "false_positives": fps,
            "fp_rate": None,
            "fp_rate_max": fp_rate_max,
            "min_samples": need,
            "reason": f"insufficient_history:{tot}<{need}",
            "gate_version": "v2",
            "lv4_gate_redesigned": True,
            "certified": False,
            "n08_full_conformance": False,
        }
    if not rb:
        return {
            "action_id": aid,
            "allowed": False,
            "total": tot,
            "false_positives": fps,
            "fp_rate": round(fps / tot, 4),
            "fp_rate_max": fp_rate_max,
            "min_samples": need,
            "reason": "rollback_action_id_required",
            "gate_version": "v2",
            "lv4_gate_redesigned": True,
            "certified": False,
            "n08_full_conformance": False,
        }
    fp_rate = fps / tot
    allowed = fp_rate < float(fp_rate_max)
    return {
        "action_id": aid,
        "allowed": allowed,
        "total": tot,
        "false_positives": fps,
        "fp_rate": round(fp_rate, 4),
        "fp_rate_max": fp_rate_max,
        "min_samples": need,
        "reason": (
            f"fp_rate={fp_rate:.4f} < {fp_rate_max}"
            if allowed
            else f"fp_rate={fp_rate:.4f} >= {fp_rate_max}"
        ),
        "gate_version": "v2",
        "lv4_gate_redesigned": True,
        "certified": False,
        "n08_full_conformance": False,
    }


def evaluate_lv4_false_positive_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N08 Lv4 误报门门槛（certified 恒 false；允许 redesigned=true）。

    Args:
        suite: ``run_lv4_false_positive_gate_suite`` 回执。
    """
    s = suite or {}
    issues: List[str] = []
    # 为什么：禁止套件自签 certified（误报门重设计 ≠ N08 全量认证）
    if s.get("certified") is True:
        issues.append("honesty_certified_flag_forbidden")
    if s.get("n08_full_conformance") is True:
        issues.append("honesty_n08_full_forbidden")
    # 为什么：本 deepen 必须声明 redesigned，防止旧门假绿冒充
    if s.get("lv4_gate_redesigned") is not True:
        issues.append("lv4_gate_redesigned_required")
    cases = s.get("cases") or []
    if cases:
        failed = [c for c in cases if isinstance(c, dict) and not c.get("ok")]
        if failed:
            issues.append(f"suite_cases_failed:{len(failed)}")
        ids = {str(c.get("id") or "") for c in cases if isinstance(c, dict)}
        missing = [x for x in _SUITE_CASES if x not in ids]
        if missing:
            issues.append(f"suite_cases_missing:{','.join(missing)}")
    elif not s.get("ok"):
        issues.append("suite_not_ok")
    return {
        "ok": not issues and bool(s.get("ok", True)),
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n08_full_conformance": False,
        "lv4_gate_redesigned": True,
        "note": "Lv4 FP gate redesign; not N08 certified",
    }


def run_lv4_false_positive_gate_suite() -> Dict[str, Any]:
    """N08 deepen：Lv4 误报门重设计套件（certified 恒 false）。"""
    cases: List[Dict[str, Any]] = []
    zero = evaluate_lv4_fp_gate(
        action_id="a1",
        total=0,
        false_positives=0,
        rollback_action_id="rb1",
        min_samples=10,
    )
    cases.append(
        {
            "id": "zero_samples_denied",
            "ok": zero.get("allowed") is False
            and "insufficient_history" in str(zero.get("reason") or ""),
            "detail": zero.get("reason") or "",
        }
    )

    high = evaluate_lv4_fp_gate(
        action_id="a1",
        total=100,
        false_positives=5,
        rollback_action_id="rb1",
        fp_rate_max=0.005,
        min_samples=10,
    )
    cases.append(
        {
            "id": "high_fp_denied",
            "ok": high.get("allowed") is False,
            "detail": high.get("reason") or "",
        }
    )

    norb = evaluate_lv4_fp_gate(
        action_id="a1",
        total=100,
        false_positives=0,
        rollback_action_id="",
        min_samples=10,
    )
    cases.append(
        {
            "id": "missing_rollback_denied",
            "ok": norb.get("allowed") is False
            and "rollback" in str(norb.get("reason") or ""),
            "detail": norb.get("reason") or "",
        }
    )

    ok = evaluate_lv4_fp_gate(
        action_id="a1",
        total=100,
        false_positives=0,
        rollback_action_id="rb1",
        fp_rate_max=0.005,
        min_samples=10,
    )
    cases.append(
        {
            "id": "healthy_allowed",
            "ok": ok.get("allowed") is True and ok.get("gate_version") == "v2",
            "detail": "",
        }
    )
    cases.append(
        {
            "id": "honesty_certified_false",
            "ok": ok.get("certified") is False
            and ok.get("n08_full_conformance") is False
            and ok.get("lv4_gate_redesigned") is True,
            "detail": "",
        }
    )

    passed = sum(1 for c in cases if c.get("ok"))
    return {
        "ok": passed == len(_SUITE_CASES),
        "passed": passed,
        "total": len(_SUITE_CASES),
        "cases": cases,
        "certified": False,
        "n08_full_conformance": False,
        "lv4_gate_redesigned": True,
        "note": "Lv4 FP gate redesign deepen; not N08 certified",
    }
