"""离线沙箱：接受预计算指标，评估一个候选并留证据（G0 最小）。

非目标：不访问生产写路径、不调用 LLM、不做真实回放引擎。
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from core.harness.evo_compute.fitness import default_ranking_profile, rank_candidates
from core.harness.evo_compute.genome_registry import get_genome
from core.harness.evo_compute.status import advance_candidate_status


def _evidence_dir() -> Path:
    """证据目录：优先 AIPLAT_HOME；不可写则回退临时目录。"""
    import tempfile

    root = os.environ.get("AIPLAT_HOME") or os.path.expanduser("~/.aiplat")
    p = Path(root) / "evo_compute" / "evidence"
    try:
        p.mkdir(parents=True, exist_ok=True)
        return p
    except OSError:
        p = Path(tempfile.gettempdir()) / "aiplat_evo_compute" / "evidence"
        p.mkdir(parents=True, exist_ok=True)
        return p


def evaluate_candidate_offline(
    *,
    genome_id: str,
    candidate_id: str = "",
    genes: Optional[Dict[str, Any]] = None,
    fitness: Optional[Dict[str, Any]] = None,
    actor: str = "system_sandbox",
    seed: int = 0,
    ranking_profile: Optional[Dict[str, Any]] = None,
    persist_evidence: bool = True,
) -> Dict[str, Any]:
    """离线评估单个候选：genome 必须已登记；指标由调用方预计算注入。

    Args:
        genome_id: 已登记 genome。
        candidate_id: 候选 id；空则自动生成。
        genes: 候选基因（仅记录，G0 不执行）。
        fitness: 预计算适应度向量（quality/cost_usd/latency_p95_ms/...）。
        actor: 评估 actor。
        seed: 可复现种子。
        ranking_profile: 排名配置。
        persist_evidence: 是否落盘证据 JSON。

    Returns:
        回执含状态变迁、排名与证据路径；``production_write`` 恒 false。
    """
    gid = str(genome_id or "").strip()
    cid = str(candidate_id or "").strip() or f"cand-{uuid.uuid4().hex[:12]}"
    act = str(actor or "system_sandbox").strip()
    fit = dict(fitness or {})
    out: Dict[str, Any] = {
        "ok": False,
        "candidate_id": cid,
        "genome_id": gid,
        "status": "draft",
        "error": "",
        "evidence_ref": "",
        "ranked": None,
        "production_write": False,
        "network_access": False,
        "g0_foundation": True,
        "certified": False,
        "e2_claimed": False,
        "sandbox": True,
    }
    g = get_genome(gid)
    if not g.get("ok"):
        out["error"] = g.get("error") or "genome_not_found"
        return out
    if not fit:
        out["error"] = "fitness_required"
        return out

    # 幸福路径走到 ranked（评估完成）；不上 production
    path = (
        ("draft", "registered"),
        ("registered", "evaluating"),
        ("evaluating", "ranked"),
    )
    status = "draft"
    transitions = []
    for fr, to in path:
        step = advance_candidate_status(
            candidate_id=cid,
            from_status=fr,
            to_status=to,
            actor=act,
            evidence_ref=f"sandbox:{cid}",
        )
        transitions.append(step)
        if not step.get("ok"):
            out["error"] = step.get("error") or "transition_failed"
            out["transitions"] = transitions
            return out
        status = str(step.get("status") or to)

    ranked = rank_candidates(
        [{"candidate_id": cid, "fitness": fit}],
        ranking_profile=ranking_profile or default_ranking_profile(),
        seed=seed,
    )
    evidence = {
        "candidate_id": cid,
        "genome_id": gid,
        "genes": dict(genes or {}),
        "fitness": fit,
        "ranked": ranked,
        "transitions": transitions,
        "seed": int(seed),
        "evaluated_at": time.time(),
        "sandbox": True,
        "production_write": False,
    }
    evidence_ref = f"memory:{cid}"
    if persist_evidence:
        epath = _evidence_dir() / f"{cid}.json"
        epath.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        evidence_ref = str(epath)
    out.update(
        {
            "ok": True,
            "status": status,
            "evidence_ref": evidence_ref,
            "evidence": evidence if not persist_evidence else None,
            "ranked": ranked,
            "transitions": transitions,
            "genome": g.get("genome"),
            "ranking_profile_id": ranked.get("ranking_profile_id"),
        }
    )
    return out
