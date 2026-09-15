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
    """Auto-tick A/B/C/D from usage + independence stats; customer-only → na."""
    from core.apps.fde.service.usage_signal import get_usage_baseline, get_usage_signal

    domain = (domain_id or "").strip()
    sig = await get_usage_signal(domain, require_domain=False, store=store)
    base: Optional[Dict[str, Any]] = None
    try:
        base = await get_usage_baseline(domain, store=store)
    except Exception:
        base = None

    st = store
    if st is None:
        from core.harness.ontology_engine.action_registry import get_action_registry

        st = get_action_registry()._store
        await st.initialize()
    indep: Dict[str, Any] = {}
    try:
        indep = await st.query_independence_stats(domain, days=90)
    except Exception as e:
        logger.warning("independence stats failed: %s", e)
        indep = {}

    cur = get_escort_exit(domain)
    cl = dict(cur.get("checklist") or {})
    a_items: List[Dict[str, Any]] = [dict(i) for i in (cl.get("A") or [])]
    c_items: List[Dict[str, Any]] = [dict(i) for i in (cl.get("C") or [])]
    b_items: List[Dict[str, Any]] = [dict(i) for i in (cl.get("B") or [])]
    d_items: List[Dict[str, Any]] = [dict(i) for i in (cl.get("D") or [])]

    def _set(items: List[Dict[str, Any]], iid: str, done: bool, **extra: Any) -> None:
        for i in items:
            if i.get("id") == iid:
                i["done"] = done
                i.update(extra)
                return

    def _thresh(items: List[Dict[str, Any]], iid: str, default: int) -> int:
        for i in items:
            if i.get("id") == iid and i.get("n") is not None:
                try:
                    return int(i["n"])
                except (TypeError, ValueError):
                    return default
        return default

    # --- A: customer independence proxies from audit ---
    n_act = int(indep.get("non_platform_actions") or 0)
    n_fail = int(indep.get("non_platform_failures") or 0)
    n_actors = int(indep.get("non_platform_actors") or 0)
    a1_n = _thresh(a_items, "a1", 10)
    a2_m = _thresh(a_items, "a2", 3)
    a4_k = _thresh(a_items, "a4", 2)
    _set(
        a_items,
        "a1",
        n_act >= a1_n,
        value=n_act,
        note="非平台 actor 的 Action 次数（90d）",
    )
    _set(
        a_items,
        "a2",
        n_fail >= a2_m,
        value=n_fail,
        note="非平台 actor 的失败次数代理「遇过异常」；非闭环证明",
    )
    _set(
        a_items,
        "a3",
        False,
        na=True,
        note="not-available：签收/归档次数需独立记录源",
    )
    ho = get_metric_handover(domain)
    contacts: List[str] = []
    for raw in (ho.get("customer_contact"), ho.get("fde_owner")):
        if not raw:
            continue
        for part in re.split(r"[,;/|]+", str(raw)):
            p = part.strip()
            if p and p not in contacts:
                contacts.append(p)
    # a4: prefer customer-side contacts only (exclude fde_owner if same list polluted)
    cust_only: List[str] = []
    for part in re.split(r"[,;/|]+", str(ho.get("customer_contact") or "")):
        p = part.strip()
        if p and p not in cust_only:
            cust_only.append(p)
    # Fallback: distinct non-platform actors as contact proxy when contacts blank
    contact_n = len(cust_only) if cust_only else n_actors
    _set(
        a_items,
        "a4",
        contact_n >= a4_k,
        value=contact_n,
        contacts=cust_only or [a.get("actor") for a in (indep.get("actors") or [])[:5]],
        note="客户联系人字段拆分，或非平台 actor 数回退",
    )

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
    # b4: Evolve rollback — leave manual / mark na if no evolve metrics wired per-domain
    for i in b_items:
        if i.get("id") == "b4" and not i.get("done"):
            i["na"] = True
            i["note"] = i.get("note") or "Evolve 回滚率按域未接线；N/A 不阻塞"

    _set(d_items, "d1", ho.get("status") == "signed", handover_status=ho.get("status"))

    cl["A"] = a_items
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
                "independence": indep,
                "quality_score": quality_score,
                "canary_ok": canary_ok,
                "evaluated_at": _now(),
            },
            "evaluated_at": _now(),
        },
        actor=actor,
    )


def _discover_peer_domain_ids() -> List[str]:
    """Domains with handover/escort artifacts under fde_customer_success/."""
    found: List[str] = []
    d = _dir()
    for p in d.glob("handover_*.json"):
        found.append(p.stem[len("handover_") :])
    for p in d.glob("escort_exit_*.json"):
        found.append(p.stem[len("escort_exit_") :])
    return found


async def list_domain_peers(
    *,
    store: Any = None,
    limit: int = 30,
) -> Dict[str, Any]:
    """Domain-level peer table for Tab⑧ (横向对照).

    Honesty: ``action_audit`` has ``domain_id`` but no customer_id, so peers are
    **domains** (e.g. lock-service vs service-domain), not multi-tenant rows
    inside one domain. True same-domain multi-customer needs a tenant key later.
    """
    from core.apps.fde.service.usage_signal import get_usage_baseline, get_usage_signal

    st = store
    if st is None:
        from core.harness.ontology_engine.action_registry import get_action_registry

        st = get_action_registry()._store
        await st.initialize()

    ids: List[str] = []
    seen = set()
    for src in (
        await st.list_audit_domains(limit=limit),
        _discover_peer_domain_ids(),
    ):
        for did in src:
            d = (did or "").strip()
            if not d or d in seen:
                continue
            seen.add(d)
            ids.append(d)
            if len(ids) >= limit:
                break
        if len(ids) >= limit:
            break

    rows: List[Dict[str, Any]] = []
    rates: List[float] = []
    calls_list: List[float] = []
    for did in ids:
        sig = await get_usage_signal(did, require_domain=False, store=st)
        base = await get_usage_baseline(did, store=st)
        ho = get_metric_handover(did)
        ex = get_escort_exit(did)
        rate = sig.get("success_rate_today") if sig.get("status") == "ok" else None
        calls = sig.get("calls_today") if sig.get("status") == "ok" else None
        if isinstance(rate, (int, float)):
            rates.append(float(rate))
        if isinstance(calls, (int, float)):
            calls_list.append(float(calls))
        rows.append(
            {
                "domain_id": did,
                "dau_today": sig.get("dau_today") if sig.get("status") == "ok" else None,
                "calls_today": calls,
                "success_rate_today": rate,
                "active_days_30d": sig.get("active_days_30d") if sig.get("status") == "ok" else None,
                "baseline_calls_median": (base or {}).get("baseline_calls_median") if base else None,
                "handover_status": ho.get("status") if "error" not in ho else None,
                "escort_status": ex.get("status") if "error" not in ex else None,
                "usage_status": sig.get("status"),
            }
        )

    peer_baseline: Dict[str, Any] = {
        "domain_count": len(rows),
        "median_success_rate": None,
        "median_calls_today": None,
        "note": "域级横向中位数；非客户 ROI；同域多客户需 tenant 键",
    }
    if rates:
        rs = sorted(rates)
        peer_baseline["median_success_rate"] = rs[len(rs) // 2]
    if calls_list:
        cs = sorted(calls_list)
        peer_baseline["median_calls_today"] = cs[len(cs) // 2]

    return {
        "status": "ok" if rows else "empty",
        "peers": rows,
        "peer_baseline": peer_baseline,
        "computed_at": _now(),
        "unit": "domain_id",
    }
