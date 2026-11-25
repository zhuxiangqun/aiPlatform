"""离散 GA 算子（Phase 2 / G2 最小）。

只进化 ``type=int`` 字段（离散组合）；浮点字段保持父代或中点。
非目标：不做 GP、不写生产、不生成核心代码。
"""
from __future__ import annotations

import hashlib
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.harness.evo_compute.de_es import genes_fingerprint, surrogate_fitness


def _rng(seed: int, salt: str = "") -> random.Random:
    """确定性 RNG。

    Args:
        seed: 主种子。
        salt: 派生盐。
    """
    h = hashlib.sha256(f"{int(seed)}:{salt}".encode("utf-8")).hexdigest()
    return random.Random(int(h[:16], 16))


def discrete_fields(fields: Sequence[Dict[str, Any]]) -> List[Tuple[str, int, int]]:
    """提取整型离散字段 (name, min, max)。

    Args:
        fields: genome.fields。
    """
    out: List[Tuple[str, int, int]] = []
    for f in fields or []:
        if str(f.get("type") or "").lower() != "int":
            continue
        name = str(f.get("name") or "").strip()
        if not name:
            continue
        lo = int(f.get("min") if f.get("min") is not None else 0)
        hi = int(f.get("max") if f.get("max") is not None else lo)
        if hi < lo:
            lo, hi = hi, lo
        out.append((name, lo, hi))
    return out


def continuous_midpoints(fields: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    """非 int 字段取中点默认值。

    Args:
        fields: genome.fields。
    """
    out: Dict[str, float] = {}
    for f in fields or []:
        if str(f.get("type") or "").lower() == "int":
            continue
        name = str(f.get("name") or "").strip()
        if not name:
            continue
        lo = float(f.get("min") if f.get("min") is not None else 0.0)
        hi = float(f.get("max") if f.get("max") is not None else 1.0)
        out[name] = (lo + hi) / 2.0
    return out


def init_discrete_individual(
    genome: Dict[str, Any],
    *,
    seed: int,
    salt: str,
) -> Dict[str, Any]:
    """初始化离散个体（int 均匀采样 + 浮点中点）。

    Args:
        genome: genome。
        seed: 种子。
        salt: 盐。
    """
    rng = _rng(seed, salt)
    genes: Dict[str, Any] = dict(continuous_midpoints(genome.get("fields") or []))
    for name, lo, hi in discrete_fields(genome.get("fields") or []):
        genes[name] = rng.randint(lo, hi)
    return genes


def ga_crossover(
    a: Dict[str, Any],
    b: Dict[str, Any],
    genome: Dict[str, Any],
    *,
    seed: int,
    salt: str,
) -> Dict[str, Any]:
    """单点/均匀混合：离散字段逐位 50% 取自父母。

    Args:
        a/b: 父母基因。
        genome: genome。
        seed: 种子。
        salt: 盐。
    """
    rng = _rng(seed, salt)
    child = dict(continuous_midpoints(genome.get("fields") or []))
    # 浮点：随机取一方
    for k in set(a) | set(b):
        if k in child:
            child[k] = a.get(k, child[k]) if rng.random() < 0.5 else b.get(k, child[k])
    for name, lo, hi in discrete_fields(genome.get("fields") or []):
        v = a.get(name, lo) if rng.random() < 0.5 else b.get(name, lo)
        try:
            iv = int(v)
        except (TypeError, ValueError):
            iv = lo
        child[name] = min(hi, max(lo, iv))
    return child


def ga_mutate(
    genes: Dict[str, Any],
    genome: Dict[str, Any],
    *,
    mutation_rate: float = 0.2,
    seed: int = 0,
    salt: str = "",
) -> Dict[str, Any]:
    """离散字段以 mutation_rate 概率重采样。

    Args:
        genes: 基因。
        genome: genome。
        mutation_rate: 突变概率。
        seed: 种子。
        salt: 盐。
    """
    rng = _rng(seed, salt)
    out = dict(genes)
    for name, lo, hi in discrete_fields(genome.get("fields") or []):
        if rng.random() < mutation_rate:
            out[name] = rng.randint(lo, hi)
        else:
            try:
                out[name] = min(hi, max(lo, int(out.get(name, lo))))
            except (TypeError, ValueError):
                out[name] = lo
    return out


def run_ga_offline(
    *,
    genome_id: str,
    population_size: int = 8,
    generations: int = 4,
    seed: int = 42,
    mutation_rate: float = 0.2,
    ranking_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """离线离散 GA 循环；硬约束零回归检查。

    Args:
        genome_id: 已登记 genome（须含至少一个 int 字段）。
        population_size: 种群。
        generations: 代数。
        seed: 种子。
        mutation_rate: 突变率。
        ranking_profile: 排名配置。

    Returns:
        回执；``g2_complete``/``certified``/``e2`` 恒 false；无生产写。
    """
    from core.harness.evo_compute.budget import check_budget
    from core.harness.evo_compute.fitness import rank_candidates
    from core.harness.evo_compute.genome_registry import get_genome
    import uuid

    g = get_genome(genome_id)
    if not g.get("ok"):
        return {
            "ok": False,
            "error": g.get("error") or "genome_not_found",
            "g2_foundation": True,
            "g2_complete": False,
            "certified": False,
            "e2_claimed": False,
            "production_write": False,
        }
    genome = g["genome"]
    dfields = discrete_fields(genome.get("fields") or [])
    if not dfields:
        return {
            "ok": False,
            "error": "no_discrete_int_fields",
            "genome_id": genome_id,
            "g2_foundation": True,
            "g2_complete": False,
            "certified": False,
            "e2_claimed": False,
            "production_write": False,
        }

    n = max(4, int(population_size))
    gens = max(1, int(generations))
    usage = {
        "candidates": 0,
        "generations": 0,
        "llm_calls": 0,
        "tokens": 0,
        "wall_time_sec": 0,
        "cost_usd": 0.0,
    }
    pop: List[Dict[str, Any]] = []
    for i in range(n):
        genes = init_discrete_individual(genome, seed=seed, salt=f"ga-init:{i}")
        fit = surrogate_fitness(
            {k: float(v) for k, v in genes.items()},
            genome,
            partition="validate",
        )
        cid = f"ga-init-{uuid.uuid4().hex[:10]}"
        pop.append(
            {
                "candidate_id": cid,
                "genes": genes,
                "fitness": fit,
                "parent_ids": [],
                "generation": 0,
                "fingerprint": genes_fingerprint(genes),
                "algorithm": "ga",
            }
        )
        usage["candidates"] += 1

    history: List[Dict[str, Any]] = []
    stopped = "completed"
    hard_regressions = 0
    for gen in range(1, gens + 1):
        usage["generations"] = gen
        bud = check_budget(usage)
        if not bud.get("within_budget"):
            stopped = "budget_exhausted"
            break
        # 按 quality 排序选父母
        ranked_pop = sorted(
            pop, key=lambda x: float(x["fitness"].get("quality") or 0), reverse=True
        )
        next_pop: List[Dict[str, Any]] = []
        # 精英保留 1
        elite = dict(ranked_pop[0], generation=gen)
        next_pop.append(elite)
        while len(next_pop) < n:
            rng = _rng(seed, f"ga-pick:{gen}:{len(next_pop)}")
            i1, i2 = rng.randrange(min(n, len(ranked_pop))), rng.randrange(
                min(n, len(ranked_pop))
            )
            p1, p2 = ranked_pop[i1], ranked_pop[i2]
            child_genes = ga_crossover(
                p1["genes"], p2["genes"], genome, seed=seed, salt=f"x:{gen}:{len(next_pop)}"
            )
            child_genes = ga_mutate(
                child_genes,
                genome,
                mutation_rate=mutation_rate,
                seed=seed,
                salt=f"m:{gen}:{len(next_pop)}",
            )
            fit = surrogate_fitness(
                {k: float(v) for k, v in child_genes.items()},
                genome,
                partition="validate",
            )
            if float(fit.get("safety_violations") or 0) > 0 or float(
                fit.get("policy_violations") or 0
            ) > 0:
                hard_regressions += 1
                continue
            cid = f"ga-{uuid.uuid4().hex[:10]}"
            next_pop.append(
                {
                    "candidate_id": cid,
                    "genes": child_genes,
                    "fitness": fit,
                    "parent_ids": [p1["candidate_id"], p2["candidate_id"]],
                    "generation": gen,
                    "fingerprint": genes_fingerprint(child_genes),
                    "algorithm": "ga",
                }
            )
            usage["candidates"] += 1
        pop = next_pop
        history.append(
            {
                "generation": gen,
                "best_quality": max(float(x["fitness"]["quality"]) for x in pop),
                "pop_size": len(pop),
            }
        )

    ranked = rank_candidates(
        [{"candidate_id": p["candidate_id"], "fitness": p["fitness"]} for p in pop],
        ranking_profile=ranking_profile,
        seed=seed,
    )
    lineage_rate = sum(1 for p in pop if isinstance(p.get("parent_ids"), list)) / max(
        len(pop), 1
    )
    by_id = {p["candidate_id"]: p for p in pop}
    ranked_full = []
    for r in ranked.get("ranked_candidates") or []:
        full = dict(by_id.get(r.get("candidate_id")) or {})
        full.update(r)
        ranked_full.append(full)

    return {
        "ok": True,
        "genome_id": genome_id,
        "algorithm": "ga",
        "seed": int(seed),
        "population_size": n,
        "generations_ran": usage["generations"],
        "stopped_reason": stopped,
        "usage": usage,
        "history": history,
        "population": pop,
        "ranked": ranked,
        "ranked_candidates": ranked_full,
        "lineage_completeness": lineage_rate,
        "hard_constraint_regressions": hard_regressions,
        "safety_regression": hard_regressions > 0,
        "discrete_fields": [n for n, _, _ in dfields],
        "production_write": False,
        "g2_foundation": True,
        "g2_complete": False,
        "certified": False,
        "e2_claimed": False,
        "note": "discrete GA offline surrogate; not production / not G2 exit",
    }
