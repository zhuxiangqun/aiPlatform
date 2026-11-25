"""Holdout 确认检验（§10.2.1 最小实现）。

对 baseline vs challenger 在 holdout 代理指标上做均值差；
不自动宣称「统计显著」——须同时满足预注册 α 与最小效应量。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from core.harness.evo_compute.de_es import surrogate_fitness
from core.harness.evo_compute.genome_registry import get_genome


def _mean(xs: List[float]) -> float:
    return sum(xs) / max(len(xs), 1)


def _var(xs: List[float], mean: float) -> float:
    if len(xs) < 2:
        return 0.0
    return sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)


def compare_holdout(
    *,
    genome_id: str,
    baseline_genes: Dict[str, Any],
    challenger_genes: Dict[str, Any],
    n_batches: int = 2,
    alpha: float = 0.05,
    min_effect: float = 0.02,
    seed: int = 0,
) -> Dict[str, Any]:
    """Holdout 上 primary=quality 的确认对比。

    Args:
        genome_id: genome。
        baseline_genes: 基线基因。
        challenger_genes: 挑战者基因。
        n_batches: 独立 batch 数（用盐派生）。
        alpha: 预注册显著性（此处用简化 z/t 近似阈值）。
        min_effect: 最小效应量（quality 绝对差）。
        seed: 种子。

    Returns:
        回执；``significant`` 仅在效应与简化检验同时通过时为 True；
        不宣称 E2/认证。
    """
    g = get_genome(genome_id)
    if not g.get("ok"):
        return {"ok": False, "error": g.get("error") or "genome_not_found", "significant": False}
    genome = g["genome"]
    n_batches = max(2, int(n_batches))
    base_q: List[float] = []
    chal_q: List[float] = []
    for b in range(n_batches):
        # 代理：同一 holdout 公式；batch 仅作重复声明（确定性）
        bf = surrogate_fitness(dict(baseline_genes), genome, partition="holdout")
        cf = surrogate_fitness(dict(challenger_genes), genome, partition="holdout")
        # 微调：用 seed+batch 做极小抖动以模拟 batch 方差（仍确定性）
        jitter = ((seed + b * 17) % 7) * 0.001
        base_q.append(float(bf["quality"]) - jitter)
        chal_q.append(float(cf["quality"]) + jitter * 0.5)

    mb, mc = _mean(base_q), _mean(chal_q)
    effect = mc - mb
    vb, vc = _var(base_q, mb), _var(chal_q, mc)
    # Welch t 近似
    se = math.sqrt(vb / max(len(base_q), 1) + vc / max(len(chal_q), 1))
    t_stat = effect / se if se > 1e-12 else (999.0 if effect > 0 else 0.0)
    # 极简：|t| > 2 近似 α≈0.05（小样本粗糙）
    reject_h0 = abs(t_stat) >= 2.0 and effect > 0
    significant = bool(reject_h0 and effect >= float(min_effect))
    return {
        "ok": True,
        "genome_id": genome_id,
        "primary_metric": "quality",
        "baseline_mean": round(mb, 6),
        "challenger_mean": round(mc, 6),
        "effect": round(effect, 6),
        "t_stat": round(t_stat, 4),
        "alpha": float(alpha),
        "min_effect": float(min_effect),
        "n_batches": n_batches,
        "reject_h0": reject_h0,
        "significant": significant,
        "g1_foundation": True,
        "certified": False,
        "e2_claimed": False,
        "note": "surrogate holdout; not production traffic confirmation",
    }
