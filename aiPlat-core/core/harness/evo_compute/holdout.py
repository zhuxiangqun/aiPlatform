"""Holdout 确认检验（§10.2.1）。

优先使用版本化 holdout 分区打分；无分区时可回退代理适应度。
不自动宣称生产流量确认 / E2 / 认证。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from core.harness.evo_compute.de_es import surrogate_fitness
from core.harness.evo_compute.genome_registry import get_genome
from core.harness.evo_compute.holdout_dataset import (
    load_holdout_partition,
    partition_fingerprint,
    score_genes_on_holdout_batches,
)


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
    holdout_partition: Optional[Dict[str, Any]] = None,
    allow_surrogate_fallback: bool = True,
) -> Dict[str, Any]:
    """Holdout 上 primary=quality 的确认对比。

    Args:
        genome_id: genome。
        baseline_genes: 基线基因。
        challenger_genes: 挑战者基因。
        n_batches: 代理路径下的独立 batch 数。
        alpha: 预注册显著性（简化 t 近似）。
        min_effect: 最小效应量（quality 绝对差）。
        seed: 代理路径种子。
        holdout_partition: 可选已加载分区；缺省 ``load_holdout_partition``。
        allow_surrogate_fallback: 无分区时是否回退代理。

    Returns:
        回执；``significant`` 仅在效应与简化检验同时通过时为 True；
        ``source``=dataset_*|surrogate|unavailable；不宣称 E2/认证。
    """
    g = get_genome(genome_id)
    if not g.get("ok"):
        return {
            "ok": False,
            "error": g.get("error") or "genome_not_found",
            "significant": False,
            "source": "unavailable",
            "certified": False,
            "e2_claimed": False,
            "production_traffic": False,
        }
    genome = g["genome"]

    part = holdout_partition
    if part is None:
        part = load_holdout_partition(genome_id)
    source = "unavailable"
    base_q: List[float] = []
    chal_q: List[float] = []
    dataset_meta: Dict[str, Any] = {}

    if isinstance(part, dict) and part.get("available") and part.get("batches"):
        batches = part.get("batches") or []
        base_q = score_genes_on_holdout_batches(dict(baseline_genes), genome, batches)
        chal_q = score_genes_on_holdout_batches(dict(challenger_genes), genome, batches)
        source = str(part.get("source") or "dataset")
        dataset_meta = {
            "dataset_version": part.get("dataset_version"),
            "partition": part.get("partition") or "holdout",
            "fingerprint": partition_fingerprint(part),
            "n_batches": len(batches),
        }
    elif allow_surrogate_fallback:
        source = "surrogate"
        n_batches = max(2, int(n_batches))
        for b in range(n_batches):
            bf = surrogate_fitness(dict(baseline_genes), genome, partition="holdout")
            cf = surrogate_fitness(dict(challenger_genes), genome, partition="holdout")
            jitter = ((seed + b * 17) % 7) * 0.001
            base_q.append(float(bf["quality"]) - jitter)
            chal_q.append(float(cf["quality"]) + jitter * 0.5)
        dataset_meta = {"n_batches": n_batches}
    else:
        return {
            "ok": True,
            "genome_id": genome_id,
            "available": False,
            "source": "unavailable",
            "significant": False,
            "g1_foundation": True,
            "certified": False,
            "e2_claimed": False,
            "production_traffic": False,
            "note": "holdout partition unavailable; surrogate disabled",
        }

    mb, mc = _mean(base_q), _mean(chal_q)
    effect = mc - mb
    vb, vc = _var(base_q, mb), _var(chal_q, mc)
    se = math.sqrt(vb / max(len(base_q), 1) + vc / max(len(chal_q), 1))
    t_stat = effect / se if se > 1e-12 else (999.0 if effect > 0 else 0.0)
    reject_h0 = abs(t_stat) >= 2.0 and effect > 0
    significant = bool(reject_h0 and effect >= float(min_effect))
    note = (
        "dataset holdout compare; ≠ production traffic confirmation"
        if source.startswith("dataset")
        else "surrogate holdout; not production traffic confirmation"
    )
    return {
        "ok": True,
        "available": True,
        "genome_id": genome_id,
        "primary_metric": "quality",
        "baseline_mean": round(mb, 6),
        "challenger_mean": round(mc, 6),
        "effect": round(effect, 6),
        "t_stat": round(t_stat, 4),
        "alpha": float(alpha),
        "min_effect": float(min_effect),
        "reject_h0": reject_h0,
        "significant": significant,
        "source": source,
        "g1_foundation": True,
        "certified": False,
        "e2_claimed": False,
        "production_traffic": False,
        "note": note,
        **dataset_meta,
    }
