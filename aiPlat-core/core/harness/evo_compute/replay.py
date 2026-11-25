"""离线回放（实施计划 §10.1 分区 + 夹具）。

接受预分区样本指标，聚合成 fitness，再走沙箱评估。
非目标：不调用 LLM、不读生产索引、不写生产配置。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.harness.evo_compute.sandbox import evaluate_candidate_offline

# 与 §10.1 对齐的分区名
REPLAY_PARTITIONS: tuple = ("tune", "validate", "holdout", "regression")


def default_replay_fixture(genome_id: str = "routing.weights.v1") -> Dict[str, Any]:
    """内置夹具：四分区各若干样本指标（确定性）。

    Args:
        genome_id: 关联 genome。

    Returns:
        夹具字典；声明为 fixture 而非生产真实回放。
    """
    # 确定性夹具；真实回放须另声明 dataset_version + source=production_sample
    samples = {
        "tune": [
            {"quality": 0.82, "cost_usd": 0.02, "latency_p95_ms": 110, "success": 1},
            {"quality": 0.78, "cost_usd": 0.025, "latency_p95_ms": 130, "success": 1},
            {"quality": 0.80, "cost_usd": 0.022, "latency_p95_ms": 120, "success": 1},
        ],
        "validate": [
            {"quality": 0.79, "cost_usd": 0.021, "latency_p95_ms": 125, "success": 1},
            {"quality": 0.81, "cost_usd": 0.019, "latency_p95_ms": 115, "success": 1},
        ],
        "holdout": [
            {"quality": 0.77, "cost_usd": 0.023, "latency_p95_ms": 128, "success": 1},
            {"quality": 0.80, "cost_usd": 0.020, "latency_p95_ms": 118, "success": 1},
        ],
        "regression": [
            {"quality": 0.75, "cost_usd": 0.03, "latency_p95_ms": 140, "success": 1},
        ],
    }
    return {
        "fixture_id": "evo_replay_fixture_g0_v1",
        "genome_id": genome_id,
        "dataset_version": "fixture_v1",
        "source": "fixture",
        "production_sample": False,
        "partitions": samples,
        "note": "fixture replay only; not production offline replay certified",
    }


def aggregate_partition_metrics(
    partitions: Dict[str, List[Dict[str, Any]]],
    *,
    use_partition: str = "validate",
) -> Dict[str, Any]:
    """将分区样本聚合成 fitness 向量。

    Args:
        partitions: 分区名 → 样本指标列表。
        use_partition: 用于选型的分区（默认 validate；holdout 留给最终确认）。

    Returns:
        fitness 字典 + 聚合元数据。
    """
    part = str(use_partition or "validate").strip()
    rows = list(partitions.get(part) or [])
    if not rows:
        return {
            "ok": False,
            "error": "partition_empty",
            "partition": part,
            "fitness": {},
        }
    n = len(rows)
    quality = sum(float(r.get("quality") or 0) for r in rows) / n
    cost = sum(float(r.get("cost_usd") or 0) for r in rows) / n
    latency = sum(float(r.get("latency_p95_ms") or 0) for r in rows) / n
    success_rate = sum(float(r.get("success") or 0) for r in rows) / n
    fitness = {
        "quality": round(quality, 6),
        "cost_usd": round(cost, 6),
        "latency_p95_ms": round(latency, 3),
        "safety_violations": 0,
        "policy_violations": 0,
        "evidence_coverage": round(min(1.0, n / 5.0), 4),
        "confidence": round(success_rate, 4),
        "success_rate": round(success_rate, 4),
    }
    return {
        "ok": True,
        "partition": part,
        "sample_count": n,
        "fitness": fitness,
        "error": "",
    }


def replay_candidate_offline(
    *,
    genome_id: str,
    genes: Optional[Dict[str, Any]] = None,
    candidate_id: str = "",
    fixture: Optional[Dict[str, Any]] = None,
    use_partition: str = "validate",
    seed: int = 0,
    persist_evidence: bool = True,
) -> Dict[str, Any]:
    """夹具离线回放 → 聚合 fitness → 沙箱评估。

    Args:
        genome_id: 已登记 genome。
        genes: 候选基因。
        candidate_id: 候选 id。
        fixture: 自定义夹具；空则用 default_replay_fixture。
        use_partition: 聚合分区。
        seed: 可复现种子。
        persist_evidence: 是否落盘沙箱证据。

    Returns:
        回执；``production_sample`` / ``certified`` 恒 false。
    """
    gid = str(genome_id or "").strip()
    fix = dict(fixture) if fixture else default_replay_fixture(gid)
    parts = fix.get("partitions") or {}
    agg = aggregate_partition_metrics(parts, use_partition=use_partition)
    out: Dict[str, Any] = {
        "ok": False,
        "genome_id": gid,
        "error": "",
        "fixture_id": fix.get("fixture_id"),
        "dataset_version": fix.get("dataset_version"),
        "source": fix.get("source") or "fixture",
        "production_sample": False,
        "production_write": False,
        "g0_foundation": True,
        "certified": False,
        "e2_claimed": False,
        "replay": True,
    }
    if not agg.get("ok"):
        out["error"] = agg.get("error") or "aggregate_failed"
        out["aggregate"] = agg
        return out
    ev = evaluate_candidate_offline(
        genome_id=gid,
        candidate_id=candidate_id or f"replay-{gid.replace('.', '-')}",
        genes=genes or {},
        fitness=agg.get("fitness") or {},
        seed=seed,
        persist_evidence=persist_evidence,
    )
    out.update(
        {
            "ok": bool(ev.get("ok")),
            "error": ev.get("error") or "",
            "candidate_id": ev.get("candidate_id"),
            "status": ev.get("status"),
            "evidence_ref": ev.get("evidence_ref"),
            "ranked": ev.get("ranked"),
            "aggregate": agg,
            "sandbox": ev,
            "partition_counts": {k: len(v or []) for k, v in parts.items()},
        }
    )
    return out
