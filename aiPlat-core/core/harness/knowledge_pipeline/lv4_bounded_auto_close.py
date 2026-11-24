"""N08 residual + 产品面：有界 Lv4 auto-close 评估（非全量 Action Lv4）。

职责：
  - residual：opt-in ``evaluate_bounded_lv4_auto_close``（env 门）
  - 产品面：默认可用 ``evaluate_bounded_lv4_auto_close_product``（无 env 门）
  - 仅 ``risk_level=low`` + ``action_level=lv4_auto_close`` + 误报门 v2
  - suite/gate：``certified`` / ``full_action_lv4`` 恒 false；freeze 仍 true

非目标：
  - 不宣称 N08 certified / 全量 Action Lv4 自动闭环产品化
  - 不绕过 kill switch / require_approval 生产执行链
  - 不做中高风险动作自动放行
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CASES = (
    "lv4_auto_close_unavailable",
    "lv4_auto_close_opt_in",
    "honesty_certified_false",
)

_PRODUCT_CASES = (
    "lv4_auto_close_product_eval",
    "lv4_auto_close_product_high_risk_denied",
    "honesty_product_certified_false",
)

_ALLOWED_RISK = frozenset({"low"})


def _evaluate_bounded_lv4_impl(
    *,
    action_id: str,
    total: int,
    false_positives: int,
    rollback_action_id: str,
    risk_level: str,
    action_level: str,
    fp_rate_max: float,
    min_samples: Optional[int],
    via: str,
    product_surface: bool,
) -> Dict[str, Any]:
    """共享有界评估（residual / 产品面共用；不检查 env）。

    Args:
        action_id: 动作 id。
        total: 历史执行条数。
        false_positives: 误报条数。
        rollback_action_id: 回滚动作 id。
        risk_level: 风险等级。
        action_level: 阶梯等级。
        fp_rate_max: 误报率上限。
        min_samples: 最小样本。
        via: ``opt_in`` 或 ``product``。
        product_surface: 是否产品面回执。
    """
    aid = str(action_id or "").strip()
    base = {
        "action_id": aid,
        "auto_close_allowed": False,
        "certified": False,
        "n08_full_conformance": False,
        "full_action_lv4": False,
        "n08_action_policy_freeze": True,
        "lv4_gate_redesigned": True,
        "bounded": True,
        "lv4_product_surface": bool(product_surface),
    }
    if not aid:
        return {**base, "status": "invalid", "error": "action_id_required"}

    level = str(action_level or "").strip().lower()
    risk = str(risk_level or "").strip().lower()
    if level != "lv4_auto_close":
        return {
            **base,
            "status": "denied",
            "via": via,
            "reason": f"action_level_not_lv4:{level or 'empty'}",
            "note": "bounded requires lv4_auto_close; not full Action Lv4",
        }
    if risk not in _ALLOWED_RISK:
        return {
            **base,
            "status": "denied",
            "via": via,
            "reason": f"risk_not_bounded:{risk or 'empty'}",
            "note": "bounded allows risk_level=low only; not full Action Lv4",
        }

    from core.harness.knowledge_pipeline.lv4_false_positive_gate import (
        evaluate_lv4_fp_gate,
    )

    gate = evaluate_lv4_fp_gate(
        action_id=aid,
        total=int(total),
        false_positives=int(false_positives),
        rollback_action_id=rollback_action_id,
        fp_rate_max=fp_rate_max,
        min_samples=min_samples,
    )
    allowed = gate.get("allowed") is True
    return {
        **base,
        "status": "ok" if allowed else "denied",
        "via": via,
        "auto_close_allowed": allowed,
        "reason": gate.get("reason") or "",
        "fp_gate": gate,
        "risk_level": risk,
        "action_level": level,
        "note": (
            "bounded lv4 auto-close product surface; "
            "not full Action Lv4 / not N08 certified"
            if product_surface
            else "bounded lv4 auto-close residual only; "
            "not full Action Lv4 / not N08 certified"
        ),
    }


def evaluate_bounded_lv4_auto_close(
    *,
    action_id: str,
    total: int,
    false_positives: int,
    rollback_action_id: str = "",
    risk_level: str = "low",
    action_level: str = "lv4_auto_close",
    fp_rate_max: float = 0.005,
    min_samples: Optional[int] = None,
) -> Dict[str, Any]:
    """N08 residual：有界 Lv4 auto-close 评估（非全量 / 非 certified）。

    默认关闭（无 ``AIPLAT_KNOWLEDGE_LV4_AUTO_CLOSE=1`` → ``lv4_auto_close_unavailable``）。
    仅 ``risk_level=low`` 且 ``action_level=lv4_auto_close`` 可进入误报门 v2。

    Args:
        action_id: 动作 id。
        total: 历史执行条数。
        false_positives: 误报条数。
        rollback_action_id: 回滚动作 id。
        risk_level: 风险等级（有界：仅 low）。
        action_level: 阶梯等级（须 lv4_auto_close）。
        fp_rate_max: 误报率上限。
        min_samples: 最小样本；缺省走 v2 默认。
    """
    aid = str(action_id or "").strip()
    base = {
        "action_id": aid,
        "auto_close_allowed": False,
        "certified": False,
        "n08_full_conformance": False,
        "full_action_lv4": False,
        "n08_action_policy_freeze": True,
        "lv4_gate_redesigned": True,
        "bounded": True,
        "lv4_product_surface": False,
    }
    if not aid:
        return {**base, "status": "invalid", "error": "action_id_required"}

    # 为什么：默认关闭有界闭环评估，避免把 FP 门误当全量 Lv4 产品
    if os.environ.get("AIPLAT_KNOWLEDGE_LV4_AUTO_CLOSE", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        return {
            **base,
            "status": "lv4_auto_close_unavailable",
            "via": "env_disabled",
            "note": "set AIPLAT_KNOWLEDGE_LV4_AUTO_CLOSE=1 to enable bounded auto-close",
        }

    return _evaluate_bounded_lv4_impl(
        action_id=aid,
        total=total,
        false_positives=false_positives,
        rollback_action_id=rollback_action_id,
        risk_level=risk_level,
        action_level=action_level,
        fp_rate_max=fp_rate_max,
        min_samples=min_samples,
        via="opt_in",
        product_surface=False,
    )


def evaluate_bounded_lv4_auto_close_product(
    *,
    action_id: str,
    total: int,
    false_positives: int,
    rollback_action_id: str = "",
    risk_level: str = "low",
    action_level: str = "lv4_auto_close",
    fp_rate_max: float = 0.005,
    min_samples: Optional[int] = None,
) -> Dict[str, Any]:
    """N08 产品面：有界 Lv4 auto-close 评估（默认可用；非全量 / 非 certified）。

    无 residual env 门。仍仅 low 风险 + lv4_auto_close + 误报门 v2。

    Args:
        action_id: 动作 id。
        total: 历史执行条数。
        false_positives: 误报条数。
        rollback_action_id: 回滚动作 id。
        risk_level: 风险等级（有界：仅 low）。
        action_level: 阶梯等级（须 lv4_auto_close）。
        fp_rate_max: 误报率上限。
        min_samples: 最小样本。
    """
    return _evaluate_bounded_lv4_impl(
        action_id=action_id,
        total=total,
        false_positives=false_positives,
        rollback_action_id=rollback_action_id,
        risk_level=risk_level,
        action_level=action_level,
        fp_rate_max=fp_rate_max,
        min_samples=min_samples,
        via="product",
        product_surface=True,
    )


def run_bounded_lv4_auto_close_suite() -> Dict[str, Any]:
    """N08 residual：有界 Lv4 auto-close 套件（certified 恒 false）。"""
    cases: List[Dict[str, Any]] = []
    prev = os.environ.get("AIPLAT_KNOWLEDGE_LV4_AUTO_CLOSE")
    os.environ.pop("AIPLAT_KNOWLEDGE_LV4_AUTO_CLOSE", None)
    try:
        unavail = evaluate_bounded_lv4_auto_close(
            action_id="n08-bounded-a1",
            total=100,
            false_positives=0,
            rollback_action_id="rb1",
            risk_level="low",
            action_level="lv4_auto_close",
            min_samples=10,
        )
        cases.append(
            {
                "id": "lv4_auto_close_unavailable",
                "ok": unavail.get("status") == "lv4_auto_close_unavailable"
                and unavail.get("certified") is False
                and unavail.get("full_action_lv4") is False
                and unavail.get("auto_close_allowed") is False
                and unavail.get("lv4_product_surface") is False,
            }
        )

        os.environ["AIPLAT_KNOWLEDGE_LV4_AUTO_CLOSE"] = "1"
        healthy = evaluate_bounded_lv4_auto_close(
            action_id="n08-bounded-a1",
            total=100,
            false_positives=0,
            rollback_action_id="rb1",
            risk_level="low",
            action_level="lv4_auto_close",
            min_samples=10,
        )
        high_risk = evaluate_bounded_lv4_auto_close(
            action_id="n08-bounded-a1",
            total=100,
            false_positives=0,
            rollback_action_id="rb1",
            risk_level="high",
            action_level="lv4_auto_close",
            min_samples=10,
        )
        cases.append(
            {
                "id": "lv4_auto_close_opt_in",
                "ok": healthy.get("status") == "ok"
                and healthy.get("auto_close_allowed") is True
                and healthy.get("certified") is False
                and healthy.get("full_action_lv4") is False
                and high_risk.get("auto_close_allowed") is False
                and "risk_not_bounded" in str(high_risk.get("reason") or ""),
            }
        )
        cases.append(
            {
                "id": "honesty_certified_false",
                "ok": healthy.get("certified") is False
                and healthy.get("n08_action_policy_freeze") is True
                and healthy.get("n08_full_conformance") is False,
            }
        )
    finally:
        if prev is None:
            os.environ.pop("AIPLAT_KNOWLEDGE_LV4_AUTO_CLOSE", None)
        else:
            os.environ["AIPLAT_KNOWLEDGE_LV4_AUTO_CLOSE"] = prev

    passed = sum(1 for c in cases if c.get("ok"))
    return {
        "ok": passed == len(_CASES) and len(cases) == len(_CASES),
        "passed": passed,
        "total": len(_CASES),
        "cases": cases,
        "certified": False,
        "n08_full_conformance": False,
        "full_action_lv4": False,
        "n08_action_policy_freeze": True,
        "lv4_gate_redesigned": True,
        "lv4_product_surface": False,
        "note": "Bounded Lv4 auto-close residual; not full Action Lv4 / not N08 certified",
    }


def evaluate_bounded_lv4_auto_close_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N08 residual：有界 Lv4 auto-close 门槛门；certified 恒 false。

    Args:
        suite: ``run_bounded_lv4_auto_close_suite`` 回执。
    """
    s = suite if isinstance(suite, dict) else run_bounded_lv4_auto_close_suite()
    issues: List[str] = []
    if not s.get("ok"):
        issues.append("suite_not_ok")
    if s.get("certified") is True or s.get("n08_full_conformance") is True:
        issues.append("honesty_certified_flag_forbidden")
    if s.get("full_action_lv4") is True:
        issues.append("honesty_full_action_lv4_forbidden")
    ids = {
        c.get("id")
        for c in (s.get("cases") or [])
        if isinstance(c, dict) and c.get("ok")
    }
    for need in _CASES:
        if need not in ids:
            issues.append(f"missing_or_failed:{need}")
    return {
        "ok": not issues,
        "issues": issues,
        "certified": False,
        "n08_full_conformance": False,
        "full_action_lv4": False,
        "n08_action_policy_freeze": True,
        "lv4_gate_redesigned": True,
        "lv4_product_surface": False,
        "note": "Bounded Lv4 auto-close residual gate; not N08 certified",
    }


def run_bounded_lv4_auto_close_product_suite() -> Dict[str, Any]:
    """N08 产品面套件：默认可用；certified / full_action_lv4 恒 false。"""
    cases: List[Dict[str, Any]] = []
    # 为什么：产品面无 env 门——显式清掉 residual 开关仍应可用
    prev = os.environ.pop("AIPLAT_KNOWLEDGE_LV4_AUTO_CLOSE", None)
    try:
        healthy = evaluate_bounded_lv4_auto_close_product(
            action_id="n08-product-a1",
            total=100,
            false_positives=0,
            rollback_action_id="rb-product",
            risk_level="low",
            action_level="lv4_auto_close",
            min_samples=10,
        )
        residual = evaluate_bounded_lv4_auto_close(
            action_id="n08-product-a1",
            total=100,
            false_positives=0,
            rollback_action_id="rb-product",
            risk_level="low",
            action_level="lv4_auto_close",
            min_samples=10,
        )
        cases.append(
            {
                "id": "lv4_auto_close_product_eval",
                "ok": healthy.get("status") == "ok"
                and healthy.get("via") == "product"
                and healthy.get("auto_close_allowed") is True
                and healthy.get("lv4_product_surface") is True
                and healthy.get("full_action_lv4") is False
                and residual.get("status") == "lv4_auto_close_unavailable",
            }
        )

        high_risk = evaluate_bounded_lv4_auto_close_product(
            action_id="n08-product-a1",
            total=100,
            false_positives=0,
            rollback_action_id="rb-product",
            risk_level="high",
            action_level="lv4_auto_close",
            min_samples=10,
        )
        cases.append(
            {
                "id": "lv4_auto_close_product_high_risk_denied",
                "ok": high_risk.get("auto_close_allowed") is False
                and high_risk.get("via") == "product"
                and "risk_not_bounded" in str(high_risk.get("reason") or ""),
            }
        )
        cases.append(
            {
                "id": "honesty_product_certified_false",
                "ok": healthy.get("certified") is False
                and healthy.get("n08_full_conformance") is False
                and healthy.get("n08_action_policy_freeze") is True
                and healthy.get("full_action_lv4") is False,
            }
        )
    finally:
        if prev is not None:
            os.environ["AIPLAT_KNOWLEDGE_LV4_AUTO_CLOSE"] = prev

    passed = sum(1 for c in cases if c.get("ok"))
    return {
        "ok": passed == len(_PRODUCT_CASES) and len(cases) == len(_PRODUCT_CASES),
        "passed": passed,
        "total": len(_PRODUCT_CASES),
        "cases": cases,
        "certified": False,
        "n08_full_conformance": False,
        "full_action_lv4": False,
        "n08_action_policy_freeze": True,
        "lv4_gate_redesigned": True,
        "lv4_product_surface": True,
        "note": (
            "Bounded Lv4 auto-close product surface; "
            "not full Action Lv4 / not N08 certified"
        ),
    }


def evaluate_bounded_lv4_auto_close_product_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N08 产品面门槛门：要求 lv4_product_surface；禁止 certified / full_action_lv4。

    Args:
        suite: ``run_bounded_lv4_auto_close_product_suite`` 回执。
    """
    s = (
        suite
        if isinstance(suite, dict)
        else run_bounded_lv4_auto_close_product_suite()
    )
    issues: List[str] = []
    if not s.get("ok"):
        issues.append("suite_not_ok")
    if s.get("certified") is True or s.get("n08_full_conformance") is True:
        issues.append("honesty_certified_flag_forbidden")
    if s.get("full_action_lv4") is True:
        issues.append("honesty_full_action_lv4_forbidden")
    if s.get("lv4_product_surface") is not True:
        issues.append("product_lv4_surface_required")
    ids = {
        c.get("id")
        for c in (s.get("cases") or [])
        if isinstance(c, dict) and c.get("ok")
    }
    for need in _PRODUCT_CASES:
        if need not in ids:
            issues.append(f"missing_or_failed:{need}")
    return {
        "ok": not issues,
        "issues": issues,
        "certified": False,
        "n08_full_conformance": False,
        "full_action_lv4": False,
        "n08_action_policy_freeze": True,
        "lv4_gate_redesigned": True,
        "lv4_product_surface": True,
        "note": "Bounded Lv4 auto-close product gate; not N08 certified",
    }


__all__ = [
    "evaluate_bounded_lv4_auto_close",
    "run_bounded_lv4_auto_close_suite",
    "evaluate_bounded_lv4_auto_close_gate",
    "evaluate_bounded_lv4_auto_close_product",
    "run_bounded_lv4_auto_close_product_suite",
    "evaluate_bounded_lv4_auto_close_product_gate",
]
