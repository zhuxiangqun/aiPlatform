"""Fitness 多目标 + Pareto→ranked（架构 §4.3.1）。

硬约束过滤 → 非支配排序 → 预注册标量化 → 并列规则。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def default_ranking_profile() -> Dict[str, Any]:
    """默认标量化权重（须版本化；禁止事后改权抬名次）。"""
    return {
        "ranking_profile_id": "scalar_v1",
        "use_knee": False,
        "weights": {
            "quality": 1.0,
            "cost": 0.25,
            "latency": 0.25,
            "safety": 1.0,
        },
        "hard_max_safety_violations": 0,
        "hard_max_policy_violations": 0,
    }


def _dominates(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """多目标：quality/evidence/confidence 越大越好；cost/latency/violations 越小越好。"""
    a_q, b_q = _f(a.get("quality")), _f(b.get("quality"))
    a_c, b_c = _f(a.get("cost_usd"), _f(a.get("cost"))), _f(b.get("cost_usd"), _f(b.get("cost")))
    a_l, b_l = _f(a.get("latency_p95_ms")), _f(b.get("latency_p95_ms"))
    a_e, b_e = _f(a.get("evidence_coverage")), _f(b.get("evidence_coverage"))
    a_n, b_n = _f(a.get("confidence")), _f(b.get("confidence"))
    a_s = _f(a.get("safety_violations")) + _f(a.get("policy_violations"))
    b_s = _f(b.get("safety_violations")) + _f(b.get("policy_violations"))
    better_or_eq = (
        a_q >= b_q
        and a_e >= b_e
        and a_n >= b_n
        and a_c <= b_c
        and a_l <= b_l
        and a_s <= b_s
    )
    strictly = (
        a_q > b_q
        or a_e > b_e
        or a_n > b_n
        or a_c < b_c
        or a_l < b_l
        or a_s < b_s
    )
    return better_or_eq and strictly


def _pareto_frontier(items: Sequence[Tuple[str, Dict[str, Any]]]) -> List[str]:
    """返回非支配候选 id 列表。"""
    frontier: List[str] = []
    for cid, fit in items:
        dominated = False
        for oid, ofit in items:
            if oid == cid:
                continue
            if _dominates(ofit, fit):
                dominated = True
                break
        if not dominated:
            frontier.append(cid)
    return frontier


def _scalar_score(fit: Dict[str, Any], weights: Dict[str, float]) -> float:
    """标量化得分（越高越好）。"""
    q = _f(fit.get("quality"))
    cost = _f(fit.get("cost_usd"), _f(fit.get("cost")))
    lat = _f(fit.get("latency_p95_ms"))
    # 简单归一：cost/latency 用 1/(1+x)
    cost_n = 1.0 / (1.0 + max(0.0, cost))
    lat_n = 1.0 / (1.0 + max(0.0, lat) / 1000.0)
    saf = _f(fit.get("safety_violations")) + _f(fit.get("policy_violations"))
    return (
        weights.get("quality", 1.0) * q
        + weights.get("cost", 0.25) * cost_n
        + weights.get("latency", 0.25) * lat_n
        - weights.get("safety", 1.0) * saf
    )


def _tie_key(cid: str, fit: Dict[str, Any]) -> Tuple[float, float, str]:
    """并列：evidence_coverage ↓, confidence ↓, genome/candidate id 字典序。"""
    return (-_f(fit.get("evidence_coverage")), -_f(fit.get("confidence")), cid)


def rank_candidates(
    candidates: Sequence[Dict[str, Any]],
    *,
    ranking_profile: Optional[Dict[str, Any]] = None,
    seed: int = 0,
) -> Dict[str, Any]:
    """对候选做硬约束过滤 + Pareto + 标量化排名。

    Args:
        candidates: 每项含 ``candidate_id`` 与 ``fitness``（或顶层指标字段）。
        ranking_profile: 预注册权重；默认 ``scalar_v1``。
        seed: 可复现种子（写入回执）。

    Returns:
        含 ``pareto_frontier`` / ``ranked_candidates`` / ``ranking_profile_id``。
    """
    profile = dict(ranking_profile or default_ranking_profile())
    pid = str(profile.get("ranking_profile_id") or "scalar_v1")
    weights = dict(profile.get("weights") or default_ranking_profile()["weights"])
    max_s = int(profile.get("hard_max_safety_violations", 0))
    max_p = int(profile.get("hard_max_policy_violations", 0))

    parsed: List[Tuple[str, Dict[str, Any]]] = []
    rejected: List[Dict[str, Any]] = []
    for raw in candidates or []:
        cid = str(raw.get("candidate_id") or "").strip()
        fit = raw.get("fitness") if isinstance(raw.get("fitness"), dict) else raw
        fit = dict(fit or {})
        if not cid:
            rejected.append({"candidate_id": "", "reason": "candidate_id_required"})
            continue
        if _f(fit.get("safety_violations")) > max_s or _f(fit.get("policy_violations")) > max_p:
            rejected.append({"candidate_id": cid, "reason": "hard_constraint"})
            continue
        parsed.append((cid, fit))

    frontier_ids = _pareto_frontier(parsed)
    frontier_set = set(frontier_ids)
    scored = []
    for cid, fit in parsed:
        if cid not in frontier_set:
            continue
        scored.append((cid, fit, _scalar_score(fit, weights)))
    scored.sort(key=lambda t: (-t[2], *_tie_key(t[0], t[1])))

    ranked = [
        {
            "candidate_id": cid,
            "scalar_score": score,
            "fitness": fit,
            "rank": i + 1,
        }
        for i, (cid, fit, score) in enumerate(scored)
    ]
    return {
        "ok": True,
        "pareto_frontier": [
            {"candidate_id": cid, "fitness": dict(fit)}
            for cid, fit in parsed
            if cid in frontier_set
        ],
        "ranked_candidates": ranked,
        "ranking_profile_id": pid,
        "seed": int(seed),
        "rejected": rejected,
        "g0_foundation": True,
        "certified": False,
        "e2_claimed": False,
    }
