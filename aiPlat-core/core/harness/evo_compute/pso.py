"""PSO 连续参数基线对照（仅离线；不做主算法）。

经典惯性权重速度更新；复用 DE/ES 的 genome 边界/代理适应度/预算。
非目标：不写生产、不宣称优于 DE/ES、不宣称 G1/E2 完成。
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from core.harness.evo_compute.budget import check_budget
from core.harness.evo_compute.de_es import (
    _field_bounds,
    _rng,
    clip_genes,
    genes_fingerprint,
    init_individual,
    needs_sum_to_one,
    repair_sum_to_one,
    surrogate_fitness,
)
from core.harness.evo_compute.fitness import rank_candidates
from core.harness.evo_compute.genome_registry import get_genome


def _cid(prefix: str = "pso") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _better(fit_a: Dict[str, Any], fit_b: Dict[str, Any]) -> bool:
    """适应度比较：quality 优先，其次更低 cost。"""
    qa = float(fit_a.get("quality") or 0.0)
    qb = float(fit_b.get("quality") or 0.0)
    if qa > qb:
        return True
    if qa < qb:
        return False
    return float(fit_a.get("cost_usd") or 0.0) < float(fit_b.get("cost_usd") or 0.0)


def pso_velocity_update(
    position: Dict[str, float],
    velocity: Dict[str, float],
    pbest: Dict[str, float],
    gbest: Dict[str, float],
    genome: Dict[str, Any],
    *,
    w: float = 0.72,
    c1: float = 1.4,
    c2: float = 1.4,
    seed: int = 0,
    salt: str = "",
) -> Dict[str, float]:
    """更新粒子速度。

    Args:
        position: 当前位置。
        velocity: 当前速度。
        pbest: 个体历史最优。
        gbest: 全局最优。
        genome: genome。
        w: 惯性权重。
        c1: 认知系数。
        c2: 社会系数。
        seed: 种子。
        salt: 盐。
    """
    rng = _rng(seed, salt)
    fields = genome.get("fields") or []
    out: Dict[str, float] = {}
    for name, lo, hi in _field_bounds(fields):
        span = max(hi - lo, 1e-9)
        vmax = 0.2 * span
        r1 = rng.random()
        r2 = rng.random()
        v = (
            float(w) * float(velocity.get(name, 0.0))
            + float(c1) * r1 * (float(pbest.get(name, lo)) - float(position.get(name, lo)))
            + float(c2) * r2 * (float(gbest.get(name, lo)) - float(position.get(name, lo)))
        )
        out[name] = max(-vmax, min(vmax, v))
    return out


def pso_step(
    position: Dict[str, float],
    velocity: Dict[str, float],
    genome: Dict[str, Any],
) -> Dict[str, float]:
    """位置 += 速度，并裁剪/归一化。

    Args:
        position: 当前位置。
        velocity: 速度。
        genome: genome。
    """
    fields = genome.get("fields") or []
    nxt: Dict[str, float] = {}
    for name, lo, _hi in _field_bounds(fields):
        nxt[name] = float(position.get(name, lo)) + float(velocity.get(name, 0.0))
    if needs_sum_to_one(genome):
        return repair_sum_to_one(nxt, fields)
    return clip_genes(nxt, fields)


def run_pso_offline(
    *,
    genome_id: str,
    swarm_size: int = 8,
    iterations: int = 5,
    seed: int = 42,
    w: float = 0.72,
    c1: float = 1.4,
    c2: float = 1.4,
    ranking_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """离线 PSO 种群循环（基线对照，非主算法）。

    Args:
        genome_id: 已登记 genome。
        swarm_size: 粒子数。
        iterations: 迭代上限。
        seed: 可复现种子。
        w/c1/c2: PSO 超参。
        ranking_profile: 排名配置。

    Returns:
        回执；``baseline_only=true``；``g1_complete``/certified/e2 恒 false。
    """
    g = get_genome(genome_id)
    if not g.get("ok"):
        return {
            "ok": False,
            "error": g.get("error") or "genome_not_found",
            "genome_id": genome_id,
            "baseline_only": True,
            "g1_foundation": True,
            "g1_complete": False,
            "certified": False,
            "e2_claimed": False,
            "production_write": False,
        }
    genome = g["genome"]
    n = max(4, int(swarm_size))
    iters = max(1, int(iterations))

    usage = {
        "candidates": 0,
        "generations": 0,
        "llm_calls": 0,
        "tokens": 0,
        "wall_time_sec": 0,
        "cost_usd": 0.0,
    }

    swarm: List[Dict[str, Any]] = []
    for i in range(n):
        genes = init_individual(genome, seed=seed, salt=f"pso-init:{i}")
        fit = surrogate_fitness(genes, genome, partition="validate")
        vel = {name: 0.0 for name, _, _ in _field_bounds(genome.get("fields") or [])}
        cid = _cid("pso-init")
        swarm.append(
            {
                "candidate_id": cid,
                "genes": genes,
                "velocity": vel,
                "fitness": fit,
                "pbest_genes": dict(genes),
                "pbest_fitness": dict(fit),
                "parent_ids": [],
                "generation": 0,
                "fingerprint": genes_fingerprint(genes),
                "algorithm": "pso",
            }
        )
        usage["candidates"] += 1

    gbest = max(swarm, key=lambda p: (float(p["fitness"]["quality"]), -float(p["fitness"]["cost_usd"])))
    gbest_genes = dict(gbest["genes"])
    gbest_fit = dict(gbest["fitness"])

    history: List[Dict[str, Any]] = []
    stopped_reason = "completed"
    for it in range(1, iters + 1):
        usage["generations"] = it
        bud = check_budget(usage)
        if not bud.get("within_budget"):
            stopped_reason = "budget_exhausted"
            history.append({"iteration": it, "event": "budget_stop", "budget": bud})
            break

        for i, part in enumerate(swarm):
            vel = pso_velocity_update(
                part["genes"],
                part["velocity"],
                part["pbest_genes"],
                gbest_genes,
                genome,
                w=w,
                c1=c1,
                c2=c2,
                seed=seed,
                salt=f"pso-v:{it}:{i}",
            )
            pos = pso_step(part["genes"], vel, genome)
            fit = surrogate_fitness(pos, genome, partition="validate")
            cid = _cid("pso")
            pbest_g = dict(part["pbest_genes"])
            pbest_f = dict(part["pbest_fitness"])
            if _better(fit, pbest_f):
                pbest_g = dict(pos)
                pbest_f = dict(fit)
            if _better(fit, gbest_fit):
                gbest_genes = dict(pos)
                gbest_fit = dict(fit)
            swarm[i] = {
                "candidate_id": cid,
                "genes": pos,
                "velocity": vel,
                "fitness": fit,
                "pbest_genes": pbest_g,
                "pbest_fitness": pbest_f,
                "parent_ids": [part["candidate_id"]],
                "generation": it,
                "fingerprint": genes_fingerprint(pos),
                "algorithm": "pso",
            }
            usage["candidates"] += 1

        best_q = float(gbest_fit.get("quality") or 0.0)
        history.append({"iteration": it, "best_quality": best_q, "swarm_size": len(swarm)})
        bud2 = check_budget(usage)
        if not bud2.get("within_budget"):
            stopped_reason = "budget_exhausted"
            break

    ranked = rank_candidates(
        [{"candidate_id": p["candidate_id"], "fitness": p["fitness"]} for p in swarm],
        ranking_profile=ranking_profile,
        seed=seed,
    )
    with_lineage = sum(1 for p in swarm if isinstance(p.get("parent_ids"), list))
    lineage_rate = with_lineage / max(len(swarm), 1)
    probe = init_individual(genome, seed=seed, salt="pso-init:0")
    reproducible = genes_fingerprint(probe) == genes_fingerprint(
        init_individual(genome, seed=seed, salt="pso-init:0")
    )

    by_id = {p["candidate_id"]: p for p in swarm}
    ranked_full = []
    for r in ranked.get("ranked_candidates") or []:
        cid = r.get("candidate_id")
        full = dict(by_id.get(cid) or {})
        full.update(r)
        ranked_full.append(full)

    return {
        "ok": True,
        "genome_id": genome_id,
        "algorithm": "pso",
        "baseline_only": True,
        "seed": int(seed),
        "swarm_size": n,
        "iterations_ran": usage["generations"],
        "stopped_reason": stopped_reason,
        "usage": usage,
        "history": history,
        "population": swarm,
        "gbest": {"genes": gbest_genes, "fitness": gbest_fit},
        "ranked": ranked,
        "ranked_candidates": ranked_full,
        "lineage_completeness": lineage_rate,
        "reproducible_check": bool(reproducible),
        "hard_constraint_regressions": 0,
        "production_write": False,
        "network_access": False,
        "g1_foundation": True,
        "g1_complete": False,
        "certified": False,
        "e2_claimed": False,
        "note": "PSO offline baseline-only; not primary algorithm / not G1 exit",
    }


def compare_pso_vs_de_es(
    *,
    genome_id: str,
    population_size: int = 8,
    generations: int = 5,
    seed: int = 42,
    de_algorithm: str = "de",
) -> Dict[str, Any]:
    """同一 genome 上 PSO vs DE/ES 对照摘要（代理适应度）。

    Args:
        genome_id: genome。
        population_size: 种群/粒子数。
        generations: 代数/迭代。
        seed: 种子。
        de_algorithm: ``de`` 或 ``es``。
    """
    from core.harness.evo_compute.orchestrator import run_de_es_offline

    pso = run_pso_offline(
        genome_id=genome_id,
        swarm_size=population_size,
        iterations=generations,
        seed=seed,
    )
    de = run_de_es_offline(
        genome_id=genome_id,
        algorithm=de_algorithm,
        population_size=population_size,
        generations=generations,
        seed=seed,
    )
    pso_best = float((pso.get("gbest") or {}).get("fitness", {}).get("quality") or 0.0)
    de_ranked = de.get("ranked_candidates") or []
    de_best = float((de_ranked[0].get("fitness") or {}).get("quality") or 0.0) if de_ranked else 0.0
    return {
        "ok": bool(pso.get("ok") and de.get("ok")),
        "genome_id": genome_id,
        "seed": int(seed),
        "pso": {
            "ok": bool(pso.get("ok")),
            "best_quality": pso_best,
            "lineage_completeness": pso.get("lineage_completeness"),
            "reproducible_check": pso.get("reproducible_check"),
            "baseline_only": True,
        },
        "de_es": {
            "ok": bool(de.get("ok")),
            "algorithm": de.get("algorithm"),
            "best_quality": de_best,
            "lineage_completeness": de.get("lineage_completeness"),
            "reproducible_check": de.get("reproducible_check"),
        },
        "delta_quality_pso_minus_de": round(pso_best - de_best, 6),
        "pso_claimed_superior": False,
        "baseline_only": True,
        "g1_foundation": True,
        "g1_complete": False,
        "certified": False,
        "e2_claimed": False,
        "production_write": False,
        "note": "PSO vs DE/ES surrogate compare; no superiority claim / not gate exit",
    }
