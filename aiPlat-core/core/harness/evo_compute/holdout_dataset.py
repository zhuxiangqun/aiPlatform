"""Holdout 分区数据集加载（生产加深 D2）。

为试点 genome 提供版本化 holdout 分区；可落盘到 ``AIPLAT_HOME``。
非目标：不采生产流量、不宣称统计认证/E2；无分区时诚实 unavailable。
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from core.harness.evo_compute.de_es import clip_genes, needs_sum_to_one, repair_sum_to_one
from core.harness.evo_compute.pilots import PILOT_GENOME_IDS

HOLDOUT_DATASET_VERSION = "evo.holdout.pilot.v1"


def _holdout_dir() -> Path:
    """Holdout 落盘目录。"""
    root = os.environ.get("AIPLAT_HOME") or os.path.expanduser("~/.aiplat")
    p = Path(root) / "evo_compute" / "holdout"
    try:
        p.mkdir(parents=True, exist_ok=True)
        return p
    except OSError:
        p = Path(tempfile.gettempdir()) / "aiplat_evo_compute" / "holdout"
        p.mkdir(parents=True, exist_ok=True)
        return p


def _safe_genome_filename(genome_id: str) -> str:
    gid = str(genome_id or "").strip() or "unknown"
    return gid.replace("/", "_").replace("\\", "_") + ".json"


def default_pilot_holdout_seed(genome_id: str) -> Dict[str, Any]:
    """试点 genome 的版本化 holdout 种子分区（非生产流量）。

    Args:
        genome_id: genome id。
    """
    gid = str(genome_id or "").strip()
    # 每 batch 含若干 case；target 用于相对质量打分
    if gid == "routing.weights.v1":
        batches = [
            {
                "batch_id": "h0",
                "cases": [
                    {"case_id": "r1", "target": {"semantic_weight": 0.5, "cost_weight": 0.3, "latency_weight": 0.2}},
                    {"case_id": "r2", "target": {"semantic_weight": 0.48, "cost_weight": 0.32, "latency_weight": 0.2}},
                ],
            },
            {
                "batch_id": "h1",
                "cases": [
                    {"case_id": "r3", "target": {"semantic_weight": 0.52, "cost_weight": 0.28, "latency_weight": 0.2}},
                    {"case_id": "r4", "target": {"semantic_weight": 0.5, "cost_weight": 0.31, "latency_weight": 0.19}},
                ],
            },
        ]
    elif gid == "retrieval.params.v1":
        batches = [
            {
                "batch_id": "h0",
                "cases": [
                    {"case_id": "k1", "target": {"top_k": 10, "score_threshold": 0.5, "rrf_weight": 0.5}},
                    {"case_id": "k2", "target": {"top_k": 12, "score_threshold": 0.45, "rrf_weight": 0.55}},
                ],
            },
            {
                "batch_id": "h1",
                "cases": [
                    {"case_id": "k3", "target": {"top_k": 8, "score_threshold": 0.55, "rrf_weight": 0.45}},
                ],
            },
        ]
    elif gid == "timeout.retry.v1":
        batches = [
            {
                "batch_id": "h0",
                "cases": [
                    {"case_id": "t1", "target": {"timeout_ms": 5000, "max_retries": 2, "backoff": 2.0}},
                    {"case_id": "t2", "target": {"timeout_ms": 8000, "max_retries": 3, "backoff": 1.5}},
                ],
            },
            {
                "batch_id": "h1",
                "cases": [
                    {"case_id": "t3", "target": {"timeout_ms": 3000, "max_retries": 1, "backoff": 2.0}},
                ],
            },
        ]
    else:
        return {
            "ok": False,
            "available": False,
            "source": "unavailable",
            "genome_id": gid,
            "dataset_version": HOLDOUT_DATASET_VERSION,
            "partition": "holdout",
            "batches": [],
            "error": "no_seed_for_genome",
            "production_traffic": False,
            "certified": False,
            "e2_claimed": False,
            "note": "no holdout seed for genome; not production traffic",
        }

    return {
        "ok": True,
        "available": True,
        "source": "dataset_seed",
        "genome_id": gid,
        "dataset_version": HOLDOUT_DATASET_VERSION,
        "partition": "holdout",
        "batches": batches,
        "n_batches": len(batches),
        "production_traffic": False,
        "certified": False,
        "e2_claimed": False,
        "note": "versioned pilot holdout seed; ≠ production traffic confirmation",
    }


def install_pilot_holdout_seeds(*, persist: bool = True) -> Dict[str, Any]:
    """将三试点 holdout 种子写入落盘目录。

    Args:
        persist: 是否写盘。
    """
    written: List[str] = []
    for gid in PILOT_GENOME_IDS:
        seed = default_pilot_holdout_seed(gid)
        if not seed.get("ok"):
            continue
        if persist:
            path = _holdout_dir() / _safe_genome_filename(gid)
            path.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            written.append(str(path))
    return {
        "ok": True,
        "written": written,
        "dataset_version": HOLDOUT_DATASET_VERSION,
        "production_traffic": False,
        "certified": False,
        "e2_claimed": False,
    }


def load_holdout_partition(
    genome_id: str,
    *,
    prefer_disk: bool = True,
    allow_seed_fallback: bool = True,
) -> Dict[str, Any]:
    """加载 genome 的 holdout 分区。

    Args:
        genome_id: genome id。
        prefer_disk: 优先读落盘。
        allow_seed_fallback: 无盘时回退内置种子。
    """
    gid = str(genome_id or "").strip()
    if prefer_disk:
        path = _holdout_dir() / _safe_genome_filename(gid)
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raw = None
            if isinstance(raw, dict) and isinstance(raw.get("batches"), list) and raw["batches"]:
                out = dict(raw)
                out["ok"] = True
                out["available"] = True
                out["source"] = "dataset_disk"
                out["genome_id"] = gid
                out["dataset_version"] = str(
                    out.get("dataset_version") or HOLDOUT_DATASET_VERSION
                )
                out["partition"] = "holdout"
                out["production_traffic"] = False
                out["certified"] = False
                out["e2_claimed"] = False
                out["path"] = str(path)
                out["note"] = "holdout partition from disk; ≠ production traffic"
                return out
    if allow_seed_fallback:
        return default_pilot_holdout_seed(gid)
    return {
        "ok": True,
        "available": False,
        "source": "unavailable",
        "genome_id": gid,
        "dataset_version": HOLDOUT_DATASET_VERSION,
        "partition": "holdout",
        "batches": [],
        "production_traffic": False,
        "certified": False,
        "e2_claimed": False,
        "note": "holdout partition unavailable",
    }


def _field_span(genome: Dict[str, Any]) -> Dict[str, tuple]:
    spans: Dict[str, tuple] = {}
    for f in genome.get("fields") or []:
        name = str(f.get("name") or "").strip()
        if not name:
            continue
        lo = float(f.get("min") if f.get("min") is not None else 0.0)
        hi = float(f.get("max") if f.get("max") is not None else 1.0)
        if hi < lo:
            lo, hi = hi, lo
        spans[name] = (lo, hi)
    return spans


def score_genes_on_holdout_batches(
    genes: Dict[str, Any],
    genome: Dict[str, Any],
    batches: Sequence[Dict[str, Any]],
) -> List[float]:
    """按 holdout batch 的 target 打 quality（确定性；非生产流量）。

    Args:
        genes: 候选基因。
        genome: genome 契约。
        batches: 分区 batches。
    """
    fields = genome.get("fields") or []
    g = clip_genes(dict(genes or {}), fields)
    if needs_sum_to_one(genome):
        g = repair_sum_to_one(g, fields)
    spans = _field_span(genome)
    scores: List[float] = []
    for batch in batches or []:
        cases = batch.get("cases") if isinstance(batch, dict) else None
        if not isinstance(cases, list) or not cases:
            scores.append(0.0)
            continue
        case_qs: List[float] = []
        for case in cases:
            if not isinstance(case, dict):
                continue
            target = case.get("target") if isinstance(case.get("target"), dict) else {}
            errs = []
            for name, (lo, hi) in spans.items():
                span = max(hi - lo, 1e-9)
                tv = target.get(name)
                try:
                    t = float(tv) if tv is not None else (lo + hi) / 2.0
                except (TypeError, ValueError):
                    t = (lo + hi) / 2.0
                errs.append(abs(float(g.get(name, t)) - t) / span)
            mean_err = sum(errs) / max(len(errs), 1)
            case_qs.append(max(0.0, min(1.0, 1.0 - mean_err)))
        scores.append(sum(case_qs) / max(len(case_qs), 1) if case_qs else 0.0)
    return scores


def partition_fingerprint(partition: Dict[str, Any]) -> str:
    """分区指纹。

    Args:
        partition: load_holdout_partition 回执。
    """
    blob = json.dumps(
        {
            "v": partition.get("dataset_version"),
            "g": partition.get("genome_id"),
            "b": partition.get("batches"),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
