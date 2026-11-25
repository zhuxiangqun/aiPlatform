"""DE / ES 连续参数算子（Phase 1 / G1 最小）。

仅操作 continuous_vector genome 字段；不做 GA/GP；不写生产配置。
"""
from __future__ import annotations

import hashlib
import math
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _rng(seed: int, salt: str = "") -> random.Random:
    """由种子派生确定性 RNG。

    Args:
        seed: 主种子。
        salt: 派生盐。
    """
    h = hashlib.sha256(f"{int(seed)}:{salt}".encode("utf-8")).hexdigest()
    return random.Random(int(h[:16], 16))


def _field_bounds(fields: Sequence[Dict[str, Any]]) -> List[Tuple[str, float, float]]:
    """提取字段名与 [min,max]。

    Args:
        fields: genome.fields。
    """
    out: List[Tuple[str, float, float]] = []
    for f in fields or []:
        name = str(f.get("name") or "").strip()
        if not name:
            continue
        lo = float(f.get("min") if f.get("min") is not None else 0.0)
        hi = float(f.get("max") if f.get("max") is not None else 1.0)
        if hi < lo:
            lo, hi = hi, lo
        out.append((name, lo, hi))
    return out


def clip_genes(genes: Dict[str, Any], fields: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    """按字段范围裁剪基因。

    Args:
        genes: 候选基因。
        fields: genome 字段定义。
    """
    out: Dict[str, float] = {}
    for name, lo, hi in _field_bounds(fields):
        v = genes.get(name)
        try:
            x = float(v)
        except (TypeError, ValueError):
            x = lo
        out[name] = min(hi, max(lo, x))
    return out


def repair_sum_to_one(genes: Dict[str, float], fields: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    """若约束要求 weights 和为 1，则归一化（失败则均匀）。

    Args:
        genes: 已裁剪基因。
        fields: genome 字段。
    """
    g = clip_genes(genes, fields)
    names = [n for n, _, _ in _field_bounds(fields)]
    if not names:
        return g
    s = sum(g.get(n, 0.0) for n in names)
    if s <= 0:
        u = 1.0 / len(names)
        return {n: u for n in names}
    return {n: g.get(n, 0.0) / s for n in names}


def needs_sum_to_one(genome: Dict[str, Any]) -> bool:
    """genome 约束是否含 sum(weights)==1 类。

    Args:
        genome: genome 字典。
    """
    for c in genome.get("constraints") or []:
        s = str(c).lower().replace(" ", "")
        if "sum" in s and ("==1" in s or "=1.0" in s or "==1.0" in s):
            return True
    return False


def init_individual(
    genome: Dict[str, Any],
    *,
    seed: int,
    salt: str,
) -> Dict[str, float]:
    """随机初始化一个个体。

    Args:
        genome: 已登记 genome。
        seed: 种子。
        salt: 派生盐。
    """
    rng = _rng(seed, salt)
    genes: Dict[str, float] = {}
    for name, lo, hi in _field_bounds(genome.get("fields") or []):
        genes[name] = lo + (hi - lo) * rng.random()
    if needs_sum_to_one(genome):
        genes = repair_sum_to_one(genes, genome.get("fields") or [])
    else:
        genes = clip_genes(genes, genome.get("fields") or [])
    return genes


def de_mutate(
    target: Dict[str, float],
    a: Dict[str, float],
    b: Dict[str, float],
    c: Dict[str, float],
    genome: Dict[str, Any],
    *,
    F: float = 0.5,
    CR: float = 0.7,
    seed: int = 0,
    salt: str = "",
) -> Dict[str, float]:
    """差分进化变异 + 二项交叉。

    Args:
        target: 当前个体。
        a/b/c: 三个不同供体。
        genome: genome。
        F: 缩放因子。
        CR: 交叉概率。
        seed: 种子。
        salt: 盐。
    """
    rng = _rng(seed, salt)
    fields = genome.get("fields") or []
    names = [n for n, _, _ in _field_bounds(fields)]
    if not names:
        return dict(target)
    trial = dict(target)
    j_rand = rng.randrange(len(names))
    for i, name in enumerate(names):
        if rng.random() < CR or i == j_rand:
            trial[name] = a.get(name, 0.0) + F * (b.get(name, 0.0) - c.get(name, 0.0))
    if needs_sum_to_one(genome):
        return repair_sum_to_one(trial, fields)
    return clip_genes(trial, fields)


def es_mutate(
    parent: Dict[str, float],
    genome: Dict[str, Any],
    *,
    sigma: float = 0.08,
    seed: int = 0,
    salt: str = "",
) -> Dict[str, float]:
    """(1+λ) 风格高斯扰动。

    Args:
        parent: 父代基因。
        genome: genome。
        sigma: 相对跨度的噪声比例。
        seed: 种子。
        salt: 盐。
    """
    rng = _rng(seed, salt)
    fields = genome.get("fields") or []
    child: Dict[str, float] = {}
    for name, lo, hi in _field_bounds(fields):
        span = max(hi - lo, 1e-9)
        child[name] = parent.get(name, lo) + rng.gauss(0.0, sigma * span)
    if needs_sum_to_one(genome):
        return repair_sum_to_one(child, fields)
    return clip_genes(child, fields)


def genes_fingerprint(genes: Dict[str, Any]) -> str:
    """基因指纹（可复现比对）。

    Args:
        genes: 基因字典。
    """
    items = sorted((str(k), round(float(v), 8)) for k, v in (genes or {}).items())
    raw = ",".join(f"{k}={v}" for k, v in items)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def surrogate_fitness(
    genes: Dict[str, float],
    genome: Dict[str, Any],
    *,
    partition: str = "validate",
) -> Dict[str, float]:
    """确定性代理适应度（离线；非生产流量）。

    路由类：靠近 (0.5,0.3,0.2) 且和为 1 → 更高 quality。
    其它：字段落在区间中部且稳定 → 更高 quality。

    Args:
        genes: 基因。
        genome: genome。
        partition: 分区标签（仅写入元数据）。
    """
    gid = str(genome.get("genome_id") or "")
    fields = genome.get("fields") or []
    g = clip_genes(genes, fields)
    if needs_sum_to_one(genome):
        g = repair_sum_to_one(g, fields)
        target = {"semantic_weight": 0.5, "cost_weight": 0.3, "latency_weight": 0.2}
        names = [n for n, _, _ in _field_bounds(fields)]
        dist = math.sqrt(sum((g.get(n, 0.0) - target.get(n, 1.0 / max(len(names), 1))) ** 2 for n in names))
        quality = max(0.0, min(1.0, 1.0 - dist))
        cost = 0.01 + 0.04 * (1.0 - quality)
        latency = 80.0 + 80.0 * (1.0 - quality)
    else:
        # 区间中点偏好
        errs = []
        for name, lo, hi in _field_bounds(fields):
            mid = (lo + hi) / 2.0
            span = max(hi - lo, 1e-9)
            errs.append(abs(g.get(name, mid) - mid) / span)
        mean_err = sum(errs) / max(len(errs), 1)
        quality = max(0.0, min(1.0, 1.0 - mean_err))
        cost = 0.015 + 0.03 * mean_err
        latency = 100.0 + 60.0 * mean_err
    # holdout 略差于 validate，避免泄漏
    if partition == "holdout":
        quality = max(0.0, quality - 0.02)
        cost *= 1.02
        latency *= 1.02
    return {
        "quality": round(quality, 6),
        "cost_usd": round(cost, 6),
        "latency_p95_ms": round(latency, 3),
        "safety_violations": 0.0,
        "policy_violations": 0.0,
        "evidence_coverage": 0.9 if partition != "holdout" else 0.85,
        "confidence": round(0.7 + 0.25 * quality, 4),
        "partition": partition,
        "genome_id": gid,
    }
