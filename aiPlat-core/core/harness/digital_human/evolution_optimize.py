"""五域最小自动优化闭环（Phase B）：只产 DRAFT/HUMAN_GATE 草稿，不写生产。

非目标：不宣称 E5；不自动改选模；不 auto_apply 本体。
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.utils.paths import get_aiplat_data_dir

logger = logging.getLogger("aiplat.digital_human.evolution_optimize")


def build_eval_remediation_plan(missing_ids: Optional[List[str]]) -> List[Dict[str, Any]]:
    """评测缺口 → 有序补测任务草稿（优先级=出现顺序权重）。

    Args:
        missing_ids: 缺失能力/库存 id。
    """
    plan: List[Dict[str, Any]] = []
    for i, mid in enumerate(missing_ids or []):
        sid = str(mid or "").strip()
        if not sid:
            continue
        plan.append(
            {
                "capability_id": sid,
                "priority": i + 1,
                "action": "add_or_fix_eval_coverage",
                "note": "人工补测/补 inventory；不自动改 runs_eval 策略",
            }
        )
        if len(plan) >= 40:
            break
    return plan


def build_fde_completion_plan(missing_ids: Optional[List[str]]) -> List[Dict[str, Any]]:
    """FDE 未完成 step → 有序补齐清单（保持传入顺序≈骨架 phase 序）。

    Args:
        missing_ids: 未 done 的 step id。
    """
    plan: List[Dict[str, Any]] = []
    for i, mid in enumerate(missing_ids or []):
        sid = str(mid or "").strip()
        if not sid:
            continue
        plan.append(
            {
                "step_id": sid,
                "order": i + 1,
                "action": "complete_delivery_step",
                "note": "人工在交付计划中推进；不自动改 plan status",
            }
        )
        if len(plan) >= 40:
            break
    return plan


def knowledge_target_state_summary(
    *,
    case_id: str,
    domain_id: str = "",
    reward_ema: float = 0.0,
) -> str:
    """知识案例目标态摘要（写入提案 guidance，非自动改图）。

    Args:
        case_id: 案例 id。
        domain_id: 域。
        reward_ema: 奖励。
    """
    return (
        f"目标态：审阅案例 {case_id}（域 {domain_id or '?'}，fitness/reward_ema={reward_ema:.2f}）"
        "→ 生成本体草稿提案；auto_apply=false，须人批后入图。"
    )


def propose_from_low_rated_trajectories(
    *,
    limit: int = 5,
    tenant_id: str = "default",
) -> Dict[str, Any]:
    """扫描低好评轨迹，自动生成 seed_qa 待批（有 user 问句时）。

    Args:
        limit: 最多新建条数。
        tenant_id: 租户。
    """
    from core.harness.digital_human.evolution_proposals import (
        create_evolution_proposal,
        list_evolution_proposals,
        STATUS_HUMAN_GATE,
    )

    traj_dir = Path(
        os.getenv("AIPLAT_TRAJECTORY_DIR") or get_aiplat_data_dir("trajectories")
    )
    created: List[str] = []
    skipped = 0
    if not traj_dir.is_dir():
        return {
            "ok": True,
            "created": [],
            "skipped": 0,
            "e5_claimed": False,
            "production_model_changed": False,
            "note": "no_traj_dir",
        }

    # 已有 seed_qa 纠偏指纹防抖
    existing_corr = set()
    for row in list_evolution_proposals(kind="seed_qa", limit=100):
        pl = row.get("payload") or {}
        c = str(pl.get("correction") or "")[:120]
        if c:
            existing_corr.add(c)

    for path in sorted(traj_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        if len(created) >= limit:
            break
        try:
            turns = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except Exception:
            logger.debug("skip traj %s", path, exc_info=True)
            continue
        last_user = ""
        for t in turns:
            if not isinstance(t, dict):
                continue
            role = str(t.get("role") or "")
            content = str(t.get("content") or "").strip()
            quality = str(t.get("quality") or "").strip().lower()
            if role == "user" and content:
                last_user = content
                continue
            if role != "assistant" or quality != "bad":
                continue
            # 优先用 gold 纠正；否则用「问句+坏答」作纠偏草稿
            corr = ""
            # look ahead not available; use bad answer as negative exemplar in correction draft
            if last_user:
                corr = f"问：{last_user[:200]}｜应避免答：{content[:200]}"
            if not corr or corr[:120] in existing_corr:
                skipped += 1
                continue
            r = create_evolution_proposal(
                kind="seed_qa",
                title="低好评会话→种子纠偏草稿",
                summary=f"自动扫描低好评轨迹 {path.stem}；待批写入种子库。",
                payload={
                    "correction": corr[:800],
                    "rating": "bad",
                    "source": "low_rated_scan",
                    "session": path.stem,
                    "auto_draft": True,
                },
                tenant_id=tenant_id,
                status=STATUS_HUMAN_GATE,
            )
            if r.get("ok"):
                created.append(str((r.get("proposal") or {}).get("id") or ""))
                existing_corr.add(corr[:120])
            else:
                skipped += 1
    return {
        "ok": True,
        "created": created,
        "skipped": skipped,
        "e5_claimed": False,
        "production_model_changed": False,
        "auto_apply": False,
    }


def optimize_pilot_genes_sandbox(genome_id: str) -> Dict[str, Any]:
    """对单试点跑短程 DE，返回最优基因草稿（沙箱，不切全局路由）。

    Args:
        genome_id: 试点 genome id。
    """
    from core.harness.evo_compute.orchestrator import run_de_es_offline
    from core.harness.evo_compute.pilots import PILOT_GENOME_IDS, register_pilot_genomes

    gid = (genome_id or "").strip()
    if gid not in PILOT_GENOME_IDS:
        return {
            "ok": False,
            "reason": "unknown_pilot_genome",
            "e5_claimed": False,
            "production_write": False,
        }
    register_pilot_genomes(persist=True)
    run = run_de_es_offline(
        genome_id=gid,
        algorithm="de",
        population_size=4,
        generations=2,
        seed=42,
    )
    top = None
    ranked = run.get("ranked_candidates") or []
    if ranked:
        top = ranked[0]
    genes = None
    if isinstance(top, dict):
        genes = top.get("genes")
        if genes is None and isinstance(top.get("candidate"), dict):
            genes = (top.get("candidate") or {}).get("genes")
    # fallback: population best
    if genes is None:
        for cand in run.get("population") or []:
            if isinstance(cand, dict) and cand.get("genes"):
                genes = cand.get("genes")
                break
    return {
        "ok": bool(run.get("ok")),
        "genome_id": gid,
        "best_genes": genes,
        "run_ok": bool(run.get("ok")),
        "production_write": False,
        "use_global_router": False,
        "e5_claimed": False,
        "e2_claimed": False,
        "note": "sandbox DE draft only; HUMAN_GATE still required",
    }
