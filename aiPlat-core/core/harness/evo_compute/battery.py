"""三试点 DE/ES 电池（Phase 1 / G1 slice-2）。

对 §9 三个低风险 genome 各跑离线 DE（可选 ES），汇总可复现率 / 血缘 / 硬约束。
非目标：不写生产、不采生产流量、不自动宣称 g1_complete。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.harness.evo_compute.holdout import compare_holdout
from core.harness.evo_compute.orchestrator import run_de_es_offline
from core.harness.evo_compute.pilots import PILOT_GENOME_IDS, register_pilot_genomes


def run_pilot_de_es_battery(
    *,
    algorithms: Optional[List[str]] = None,
    population_size: int = 6,
    generations: int = 2,
    seed: int = 42,
    register_pilots: bool = True,
    run_holdout: bool = True,
) -> Dict[str, Any]:
    """对三试点各跑 DE/ES，汇总 Gate G1 关键指标。

    Args:
        algorithms: 算法列表，默认 ``["de"]``。
        population_size: 种群大小。
        generations: 代数。
        seed: 可复现种子。
        register_pilots: 是否先登记三试点。
        run_holdout: 是否对每个试点做 baseline vs best 的 holdout 确认。

    Returns:
        回执含 per-genome 结果与汇总；``g1_complete``/``certified``/``e2`` 恒 false。
    """
    algos = [str(a).strip().lower() for a in (algorithms or ["de"])]
    algos = [a for a in algos if a in ("de", "es")] or ["de"]
    if register_pilots:
        reg = register_pilot_genomes(persist=False)
        if not reg.get("ok"):
            return {
                "ok": False,
                "error": "pilot_register_failed",
                "register": reg,
                "g1_foundation": True,
                "g1_complete": False,
                "certified": False,
                "e2_claimed": False,
                "production_write": False,
            }

    per_genome: List[Dict[str, Any]] = []
    repro_flags: List[bool] = []
    lineage_rates: List[float] = []
    hard_ok_flags: List[bool] = []
    holdout_hits: List[str] = []

    for gid in PILOT_GENOME_IDS:
        genome_runs: List[Dict[str, Any]] = []
        best_genes: Optional[Dict[str, Any]] = None
        best_q = -1.0
        for algo in algos:
            run = run_de_es_offline(
                genome_id=gid,
                algorithm=algo,
                population_size=population_size,
                generations=generations,
                seed=seed,
            )
            genome_runs.append(
                {
                    "algorithm": algo,
                    "ok": bool(run.get("ok")),
                    "lineage_completeness": float(run.get("lineage_completeness") or 0),
                    "reproducible_check": bool(run.get("reproducible_check")),
                    "hard_constraint_regressions": int(
                        run.get("hard_constraint_regressions", 1)
                    ),
                    "ranked_top": (run.get("ranked_candidates") or [None])[0],
                    "production_write": bool(run.get("production_write")),
                }
            )
            if run.get("ok"):
                repro_flags.append(bool(run.get("reproducible_check")))
                lineage_rates.append(float(run.get("lineage_completeness") or 0))
                hard_ok_flags.append(int(run.get("hard_constraint_regressions", 1)) == 0)
                top = (run.get("ranked_candidates") or [{}])[0]
                q = float((top.get("fitness") or {}).get("quality") or -1)
                if q > best_q and top.get("genes"):
                    best_q = q
                    best_genes = dict(top.get("genes") or {})

        hold: Optional[Dict[str, Any]] = None
        if run_holdout and best_genes is not None:
            # 朴素基线：均匀 / 中点偏好的反面——对权重类用近似均匀
            baseline = {k: round(1.0 / max(len(best_genes), 1), 6) for k in best_genes}
            # 非权重字段：用区间中点近似（由 holdout 内 clip）
            hold = compare_holdout(
                genome_id=gid,
                baseline_genes=baseline,
                challenger_genes=best_genes,
                n_batches=4,
                seed=seed,
            )
            if hold.get("significant"):
                holdout_hits.append(gid)

        per_genome.append(
            {
                "genome_id": gid,
                "runs": genome_runs,
                "ok": all(r.get("ok") for r in genome_runs),
                "holdout": hold,
            }
        )

    n = max(len(repro_flags), 1)
    repro_rate = sum(1 for x in repro_flags if x) / n
    lineage_min = min(lineage_rates) if lineage_rates else 0.0
    hard_ok = all(hard_ok_flags) if hard_ok_flags else False
    all_genomes_ok = all(g.get("ok") for g in per_genome) and len(per_genome) == len(
        PILOT_GENOME_IDS
    )

    any_prod = any(
        bool(r.get("production_write")) for g in per_genome for r in (g.get("runs") or [])
    )
    return {
        "ok": bool(all_genomes_ok) and not any_prod,
        "genome_ids": list(PILOT_GENOME_IDS),
        "algorithms": algos,
        "per_genome": per_genome,
        "summary": {
            "reproducible_rate": round(repro_rate, 4),
            "lineage_min": round(lineage_min, 4),
            "hard_constraint_ok": hard_ok,
            "holdout_significant_genomes": holdout_hits,
            "holdout_significant_count": len(holdout_hits),
            "meets_repro_gate": repro_rate >= 0.95,
            "meets_lineage_gate": lineage_min >= 1.0,
            "meets_hard_gate": hard_ok,
            "meets_holdout_gate": len(holdout_hits) >= 1,
        },
        "production_write": False,
        "production_sample": False,
        "g1_foundation": True,
        "g1_complete": False,
        "certified": False,
        "e2_claimed": False,
        "note": "three-pilot surrogate battery; not production holdout / not G1 exit claim",
    }
