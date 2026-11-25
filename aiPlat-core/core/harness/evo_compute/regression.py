"""自动回归门（Phase 2 / G2 slice-3；§10.1 regression 分区）。

在冻结 ``regression`` 集（+ 固定对抗样本）上对比 baseline vs challenger。
进化循环禁止消费本模块分数；集变更须升 ``dataset_version``。

非目标：不读生产流量、不写生产、不宣称 E2/G2 完成。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from core.harness.evo_compute.de_es import surrogate_fitness
from core.harness.evo_compute.genome_registry import get_genome
from core.harness.evo_compute.replay import default_replay_fixture

# 冻结夹具版本；变更必须升版（诚实锁）
REGRESSION_DATASET_VERSION = "regression_fixture_v1"


def default_adversarial_cases() -> List[Dict[str, Any]]:
    """固定对抗样本（夹具；非生产攻击流量）。

    Returns:
        对抗用例列表（质量/延迟压力）。
    """
    return [
        {
            "case_id": "adv.latency_spike",
            "quality": 0.70,
            "cost_usd": 0.04,
            "latency_p95_ms": 220,
            "success": 1,
            "adversarial": True,
        },
        {
            "case_id": "adv.quality_floor",
            "quality": 0.68,
            "cost_usd": 0.035,
            "latency_p95_ms": 180,
            "success": 1,
            "adversarial": True,
        },
    ]


def default_regression_set(
    *,
    genome_id: str = "timeout.retry.v1",
    dataset_version: str = REGRESSION_DATASET_VERSION,
) -> Dict[str, Any]:
    """组装冻结回归集 = replay.regression 分区 + 对抗样本。

    Args:
        genome_id: 关联 genome。
        dataset_version: 数据集版本；须与 ``REGRESSION_DATASET_VERSION`` 一致才标记 frozen。

    Returns:
        回归集回执；``production_sample`` 恒 false。
    """
    fix = default_replay_fixture(genome_id=genome_id)
    base_rows = list((fix.get("partitions") or {}).get("regression") or [])
    rows = [dict(r) for r in base_rows] + default_adversarial_cases()
    ver = str(dataset_version or "").strip() or REGRESSION_DATASET_VERSION
    return {
        "ok": True,
        "genome_id": genome_id,
        "dataset_version": ver,
        "frozen": ver == REGRESSION_DATASET_VERSION,
        "source": "fixture",
        "production_sample": False,
        "partition": "regression",
        "n_cases": len(rows),
        "cases": rows,
        "note": "fixture regression set; bump dataset_version on any change",
    }


def _aggregate_quality(rows: Sequence[Dict[str, Any]]) -> float:
    """样本 quality 均值。"""
    xs = [float(r.get("quality") or 0) for r in rows]
    return sum(xs) / max(len(xs), 1)


def evaluate_regression_case(
    *,
    genes: Dict[str, Any],
    genome: Dict[str, Any],
    case: Dict[str, Any],
) -> Dict[str, Any]:
    """单条回归用例：代理适应度相对用例地板。

    Args:
        genes: 候选基因。
        genome: genome。
        case: 回归/对抗用例。

    Returns:
        单条结果（pass = quality 不低于用例地板且无安全违规）。
    """
    fit = surrogate_fitness(dict(genes), genome, partition="regression")
    floor = float(case.get("quality") or 0)
    # 对抗用例允许略低缓冲；仍不得安全回归
    buf = 0.03 if case.get("adversarial") else 0.0
    q = float(fit.get("quality") or 0)
    safety = float(fit.get("safety_violations") or 0)
    policy = float(fit.get("policy_violations") or 0)
    ok = q + buf >= floor and safety <= 0.0 and policy <= 0.0
    return {
        "case_id": str(case.get("case_id") or case.get("id") or "anon"),
        "pass": ok,
        "quality": q,
        "floor": floor,
        "safety_violations": safety,
        "policy_violations": policy,
        "adversarial": bool(case.get("adversarial")),
    }


def run_regression_gate(
    *,
    genome_id: str,
    baseline_genes: Dict[str, Any],
    challenger_genes: Dict[str, Any],
    dataset_version: str = REGRESSION_DATASET_VERSION,
    max_quality_drop: float = 0.02,
    regression_set: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """回归门：challenger 不得相对 baseline 在冻结集上质量塌陷或安全变差。

    Args:
        genome_id: genome。
        baseline_genes: 基线基因。
        challenger_genes: 挑战者基因。
        dataset_version: 须匹配冻结版本。
        max_quality_drop: 允许的最大 quality 均值下降。
        regression_set: 可选外部集；默认 ``default_regression_set``。

    Returns:
        回执；``passed`` 表示门通过；``g2_complete``/certified/e2 恒 false；
        ``feeds_evolution`` 恒 false。
    """
    g = get_genome(genome_id)
    if not g.get("ok"):
        return {
            "ok": False,
            "error": g.get("error") or "genome_not_found",
            "passed": False,
            "feeds_evolution": False,
            "g2_foundation": True,
            "g2_complete": False,
            "certified": False,
            "e2_claimed": False,
        }
    genome = g["genome"]
    rset = regression_set or default_regression_set(
        genome_id=genome_id, dataset_version=dataset_version
    )
    ver = str(rset.get("dataset_version") or dataset_version)
    frozen_ok = bool(rset.get("frozen")) and ver == REGRESSION_DATASET_VERSION
    cases = list(rset.get("cases") or [])
    base_rows = [
        evaluate_regression_case(genes=baseline_genes, genome=genome, case=c)
        for c in cases
    ]
    chal_rows = [
        evaluate_regression_case(genes=challenger_genes, genome=genome, case=c)
        for c in cases
    ]
    bq = sum(float(r["quality"]) for r in base_rows) / max(len(base_rows), 1)
    cq = sum(float(r["quality"]) for r in chal_rows) / max(len(chal_rows), 1)
    drop = bq - cq
    base_fail = sum(1 for r in base_rows if not r["pass"])
    chal_fail = sum(1 for r in chal_rows if not r["pass"])
    safety_reg = any(
        float(c.get("safety_violations") or 0) > float(b.get("safety_violations") or 0)
        for b, c in zip(base_rows, chal_rows)
    )
    # 门：冻结集有效 + 失败数不增 + 质量下降 ≤ 阈值 + 无安全变差
    passed = (
        frozen_ok
        and chal_fail <= base_fail
        and drop <= float(max_quality_drop) + 1e-12
        and not safety_reg
    )
    return {
        "ok": True,
        "passed": passed,
        "genome_id": genome_id,
        "dataset_version": ver,
        "frozen_ok": frozen_ok,
        "n_cases": len(cases),
        "baseline_mean_quality": round(bq, 6),
        "challenger_mean_quality": round(cq, 6),
        "quality_drop": round(drop, 6),
        "max_quality_drop": float(max_quality_drop),
        "baseline_failures": base_fail,
        "challenger_failures": chal_fail,
        "safety_regression": safety_reg,
        "baseline_cases": base_rows,
        "challenger_cases": chal_rows,
        "production_sample": False,
        "feeds_evolution": False,
        "g2_foundation": True,
        "g2_complete": False,
        "certified": False,
        "e2_claimed": False,
        "note": (
            "auto regression gate on frozen fixture set; "
            "scores must not feed GA/DE-ES; not production L4 claim"
        ),
    }
