"""FDE customer-success artifacts — metric handover + escort exit.

Contracts:
  docs/contracts/FDE_BUSINESS_METRIC_HANDOVER.md
  docs/contracts/FDE_ESCORT_EXIT_CHECKLIST.md

Persists JSON under $AIPLAT_HOME/fde_customer_success/ (no ROI computation).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")))


def _dir() -> Path:
    d = _home() / "fde_customer_success"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_id(raw: str) -> str:
    s = _SAFE.sub("_", (raw or "").strip())[:120]
    return s or "unknown"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _handover_path(domain_id: str) -> Path:
    return _dir() / f"handover_{_safe_id(domain_id)}.json"


def _exit_path(domain_id: str) -> Path:
    return _dir() / f"escort_exit_{_safe_id(domain_id)}.json"


def _default_handover(domain_id: str, *, customer_name: str = "") -> Dict[str, Any]:
    return {
        "doc_id": f"FDE-HANDOVER-METRIC-{_safe_id(domain_id)}",
        "version": "v0.1",
        "domain_id": domain_id,
        "customer_name": customer_name or "",
        "fde_owner": "",
        "customer_contact": "",
        "handover_date": "",
        "status": "draft",  # draft | confirmed | signed
        "platform_baselines": {
            "action_calls_per_day": None,
            "action_success_rate": None,
            "audit_completeness": None,
            "canary_anomalies_per_week": None,
            "evolve_rollback_rate": None,
            "quality_score": None,
        },
        "customer_baselines": [],
        "joint_items": [],
        "subjective_items": [],
        "usage_snapshot": None,
        "confirmations": {
            "baseline_checked": False,
            "datasource_ok": False,
            "owners_clear": False,
            "windows_agreed": False,
        },
        "notes": "",
        "updated_at": _now(),
        "boundary": "Not ROI. Platform records baselines; customer owns P2 metrics.",
    }


def _default_exit(domain_id: str) -> Dict[str, Any]:
    return {
        "doc_id": f"FDE-EXIT-{_safe_id(domain_id)}",
        "version": "v0.1",
        "domain_id": domain_id,
        "status": "evaluating",  # evaluating | can_exit | extend | light_support
        "evaluated_at": "",
        "fde_owner": "",
        "customer_contact": "",
        "groups": {
            "A_independence": {"ok": False, "notes": ""},
            "B_stability": {"ok": False, "notes": ""},
            "C_usage": {"ok": False, "notes": ""},
            "D_handover": {"ok": False, "notes": ""},
            "E_residuals": {"ok": True, "notes": ""},
        },
        "checklist": {
            "A": [
                {"id": "a1", "label": "客户管理员独立 Action ≥ N", "done": False, "n": 10},
                {"id": "a2", "label": "客户独立处理异常 ≥ M", "done": False, "n": 3},
                {"id": "a3", "label": "客户独立签收/归档 ≥ K", "done": False, "n": 2},
                {"id": "a4", "label": "联系人 ≥ 2（非单点）", "done": False, "n": 2},
            ],
            "B": [
                {"id": "b1", "label": "质量分连续达标", "done": False},
                {"id": "b2", "label": "Action 成功率 ≥ 95%", "done": False},
                {"id": "b3", "label": "无未处理高危 canary", "done": False},
                {"id": "b4", "label": "Evolve 回滚率可接受或 N/A", "done": False},
            ],
            "C": [
                {"id": "c1", "label": "日活操作人数 (S1) ≥ 2", "done": False},
                {"id": "c2", "label": "Action 日调用 (S2) ≥ 基线 70%", "done": False},
                {"id": "c3", "label": "旁路率 ≤ 20% 或 not-available", "done": False, "na": False},
                {"id": "c4", "label": "登录频率或 not-available", "done": False, "na": False},
            ],
            "D": [
                {"id": "d1", "label": "业务指标交接单已签署", "done": False},
                {"id": "d2", "label": "SOP 已签署", "done": False},
                {"id": "d3", "label": "培训沙盒完成", "done": False},
                {"id": "d4", "label": "退出后支持渠道明确", "done": False},
            ],
        },
        "residuals": [],
        "auto_signals": None,
        "conclusion": "",
        "next_review_date": "",
        "updated_at": _now(),
        "principle": "Exit by conditions, not calendar alone.",
    }


def get_metric_handover(domain_id: str) -> Dict[str, Any]:
    domain = (domain_id or "").strip()
    if not domain:
        return {"status": "unavailable", "error": "domain_id required"}
    path = _handover_path(domain)
    if not path.exists():
        return _default_handover(domain)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("domain_id", domain)
            return data
    except Exception as e:
        logger.warning("read handover failed: %s", e)
    return _default_handover(domain)


def save_metric_handover(
    domain_id: str,
    patch: Optional[Dict[str, Any]] = None,
    *,
    actor: str = "fde",
) -> Dict[str, Any]:
    domain = (domain_id or "").strip()
    if not domain:
        return {"status": "unavailable", "error": "domain_id required"}
    cur = get_metric_handover(domain)
    if cur.get("error") == "domain_id required":
        return cur
    patch = patch or {}
    for k, v in patch.items():
        if k in ("domain_id", "doc_id"):
            continue
        if k in ("platform_baselines", "confirmations") and isinstance(v, dict):
            base = dict(cur.get(k) or {})
            base.update(v)
            cur[k] = base
        else:
            cur[k] = v
    cur["domain_id"] = domain
    cur["updated_at"] = _now()
    cur["updated_by"] = actor
    path = _handover_path(domain)
    path.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    return cur


async def refresh_handover_from_usage(
    domain_id: str,
    *,
    actor: str = "fde",
    quality_score: Optional[float] = None,
) -> Dict[str, Any]:
    """Fill P1 baselines from live usage signal (honest; no ROI)."""
    from core.apps.fde.service.usage_signal import get_usage_signal

    domain = (domain_id or "").strip()
    sig = await get_usage_signal(domain, require_domain=False)
    cur = get_metric_handover(domain)
    pb = dict(cur.get("platform_baselines") or {})
    if sig.get("status") == "ok":
        if sig.get("calls_today") is not None:
            pb["action_calls_per_day"] = sig.get("calls_today")
        if sig.get("success_rate_today") is not None:
            pb["action_success_rate"] = sig.get("success_rate_today")
    if quality_score is not None:
        pb["quality_score"] = quality_score
    return save_metric_handover(
        domain,
        {"platform_baselines": pb, "usage_snapshot": sig},
        actor=actor,
    )


def get_escort_exit(domain_id: str) -> Dict[str, Any]:
    domain = (domain_id or "").strip()
    if not domain:
        return {"status": "unavailable", "error": "domain_id required"}
    path = _exit_path(domain)
    if not path.exists():
        return _default_exit(domain)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("domain_id", domain)
            return data
    except Exception as e:
        logger.warning("read escort exit failed: %s", e)
    return _default_exit(domain)


def save_escort_exit(
    domain_id: str,
    patch: Optional[Dict[str, Any]] = None,
    *,
    actor: str = "fde",
) -> Dict[str, Any]:
    domain = (domain_id or "").strip()
    if not domain:
        return {"status": "unavailable", "error": "domain_id required"}
    cur = get_escort_exit(domain)
    if cur.get("error") == "domain_id required":
        return cur
    patch = patch or {}
    for k, v in patch.items():
        if k in ("domain_id", "doc_id"):
            continue
        if k == "groups" and isinstance(v, dict):
            base = dict(cur.get("groups") or {})
            base.update(v)
            cur["groups"] = base
        elif k == "checklist" and isinstance(v, dict):
            base = dict(cur.get("checklist") or {})
            for gk, items in v.items():
                if isinstance(items, list):
                    base[gk] = items
            cur["checklist"] = base
        else:
            cur[k] = v
    cur["domain_id"] = domain
    cur["updated_at"] = _now()
    cur["updated_by"] = actor

    cl = cur.get("checklist") or {}
    groups = dict(cur.get("groups") or {})
    for letter, gkey in (
        ("A", "A_independence"),
        ("B", "B_stability"),
        ("C", "C_usage"),
        ("D", "D_handover"),
    ):
        items = cl.get(letter) or []
        if items and isinstance(items, list):
            ok = all(
                bool(i.get("done")) or bool(i.get("na"))
                for i in items
                if isinstance(i, dict)
            )
            g = dict(groups.get(gkey) or {})
            g["ok"] = ok
            groups[gkey] = g
    cur["groups"] = groups
    all_ok = all(
        bool((groups.get(k) or {}).get("ok"))
        for k in ("A_independence", "B_stability", "C_usage", "D_handover", "E_residuals")
    )
    if patch.get("status") not in ("can_exit", "extend", "light_support", "evaluating"):
        if all_ok:
            cur["status"] = "can_exit"
            cur["conclusion"] = cur.get("conclusion") or "条件达标，可评估退出"
    path = _exit_path(domain)
    path.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    return cur


async def evaluate_escort_exit_from_signals(
    domain_id: str,
    *,
    actor: str = "fde",
    quality_score: Optional[float] = None,
    quality_ok: Optional[bool] = None,
    canary_ok: Optional[bool] = None,
    baseline_calls: Optional[float] = None,
    store: Any = None,
) -> Dict[str, Any]:
    """Auto-tick C (and parts of B) from usage signals; customer-side → not-available."""
    from core.apps.fde.service.usage_signal import get_usage_baseline, get_usage_signal

    domain = (domain_id or "").strip()
    sig = await get_usage_signal(domain, require_domain=False, store=store)
    base: Optional[Dict[str, Any]] = None
    try:
        base = await get_usage_baseline(domain, store=store)
    except Exception:
        base = None

    cur = get_escort_exit(domain)
    cl = dict(cur.get("checklist") or {})
    c_items: List[Dict[str, Any]] = [dict(i) for i in (cl.get("C") or [])]
    b_items: List[Dict[str, Any]] = [dict(i) for i in (cl.get("B") or [])]
    d_items: List[Dict[str, Any]] = [dict(i) for i in (cl.get("D") or [])]

    def _set(items: List[Dict[str, Any]], iid: str, done: bool, **extra: Any) -> None:
        for i in items:
            if i.get("id") == iid:
                i["done"] = done
                i.update(extra)
                return

    dau = int(sig.get("dau_today") or 0) if sig.get("status") == "ok" else 0
    calls = int(sig.get("calls_today") or 0) if sig.get("status") == "ok" else 0
    rate = sig.get("success_rate_today") if sig.get("status") == "ok" else None

    _set(c_items, "c1", dau >= 2, value=dau)
    bl = baseline_calls
    if bl is None and isinstance(base, dict):
        bl = base.get("baseline_calls_median")
    if bl is None or float(bl or 0) <= 0:
        _set(c_items, "c2", False, value=calls, note="基线未采集")
    else:
        _set(c_items, "c2", calls >= 0.7 * float(bl), value=calls, baseline=bl)
    for iid in ("c3", "c4"):
        for i in c_items:
            if i.get("id") == iid and not i.get("done"):
                i["na"] = True
                i["note"] = i.get("note") or "not-available"

    if rate is not None:
        _set(b_items, "b2", float(rate) >= 0.95, value=rate)
    if quality_ok is not None:
        _set(b_items, "b1", bool(quality_ok), value=quality_score)
    elif quality_score is not None:
        _set(b_items, "b1", float(quality_score) >= 60, value=quality_score)
    if canary_ok is not None:
        _set(b_items, "b3", bool(canary_ok))

    ho = get_metric_handover(domain)
    _set(d_items, "d1", ho.get("status") == "signed", handover_status=ho.get("status"))

    cl["C"] = c_items
    cl["B"] = b_items
    cl["D"] = d_items
    return save_escort_exit(
        domain,
        {
            "checklist": cl,
            "auto_signals": {
                "usage": sig,
                "baseline": base,
                "quality_score": quality_score,
                "canary_ok": canary_ok,
                "evaluated_at": _now(),
            },
            "evaluated_at": _now(),
        },
        actor=actor,
    )
