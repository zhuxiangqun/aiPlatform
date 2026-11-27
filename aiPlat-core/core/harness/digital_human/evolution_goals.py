"""五域受控自进化机读目标（规格 + 可测回执）。

非目标：不宣称 E5；不自动改全局选模；测量失败诚实返回 meets=false。
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.utils.paths import get_aiplat_data_dir, get_aiplat_home

logger = logging.getLogger("aiplat.digital_human.evolution_goals")

GOAL_CONSULTANT_SFT = "consultant.sft_quality.v1"
GOAL_EVAL_COVERAGE = "eval.coverage.v1"
GOAL_FDE_EVIDENCE = "fde.evidence.v1"
GOAL_KNOWLEDGE_FITNESS = "knowledge.case_fitness.v1"
GOAL_EVO_PILOT = "evo.pilot_sandbox.v1"

GOAL_IDS = (
    GOAL_CONSULTANT_SFT,
    GOAL_EVAL_COVERAGE,
    GOAL_FDE_EVIDENCE,
    GOAL_KNOWLEDGE_FITNESS,
    GOAL_EVO_PILOT,
)

# 顾问策展好评率门限（与结构 holdout AND）
CONSULTANT_GOOD_RATE_THRESHOLD = 0.70
# 知识案例平均 reward 门限
KNOWLEDGE_FITNESS_THRESHOLD = 0.80
# 知识待批堆积告警（条）
KNOWLEDGE_PENDING_BACKLOG_MAX = 20


def _base_honesty() -> Dict[str, Any]:
    return {
        "e5_claimed": False,
        "production_model_changed": False,
        "auto_apply": False,
        "feeds_production_routing": False,
    }


def _goal_specs() -> Dict[str, Dict[str, Any]]:
    from core.harness.evo_compute.coverage import EVAL_THRESHOLD, FDE_THRESHOLD
    from core.harness.evo_compute.pilots import PILOT_GENOME_IDS

    return {
        GOAL_CONSULTANT_SFT: {
            "goal_id": GOAL_CONSULTANT_SFT,
            "domain": "consultant",
            "metric": "good_rate",
            "threshold": CONSULTANT_GOOD_RATE_THRESHOLD,
            "how_measured": "trajectories quality good/(good+bad); AND structural holdout",
            "non_goals": [
                "live traffic eval",
                "auto bind best_model_for_purpose",
                "E5",
            ],
            "auto_apply": False,
        },
        GOAL_EVAL_COVERAGE: {
            "goal_id": GOAL_EVAL_COVERAGE,
            "domain": "eval",
            "metric": "coverage",
            "threshold": float(EVAL_THRESHOLD),
            "how_measured": "eval_inventory covered_ids/required_ids",
            "non_goals": ["auto change runs_eval policy", "E5"],
            "auto_apply": False,
        },
        GOAL_FDE_EVIDENCE: {
            "goal_id": GOAL_FDE_EVIDENCE,
            "domain": "fde",
            "metric": "coverage",
            "threshold": float(FDE_THRESHOLD),
            "how_measured": "delivery_plan skeleton steps done vs required",
            "non_goals": ["auto mutate delivery plan status", "E5"],
            "auto_apply": False,
        },
        GOAL_KNOWLEDGE_FITNESS: {
            "goal_id": GOAL_KNOWLEDGE_FITNESS,
            "domain": "knowledge",
            "metric": "mean_reward_ema",
            "threshold": KNOWLEDGE_FITNESS_THRESHOLD,
            "how_measured": "mean reward_ema of high-reward cases; pending backlog alert",
            "non_goals": ["auto_apply ontology graph", "E5"],
            "auto_apply": False,
        },
        GOAL_EVO_PILOT: {
            "goal_id": GOAL_EVO_PILOT,
            "domain": "evo_pilot",
            "metric": "pilot_ready_ratio",
            "threshold": 1.0,
            "how_measured": "3 pilot genomes each have HUMAN_GATE|APPROVED|APPLIED proposal",
            "non_goals": [
                "production optimal claim",
                "use_global_router by default",
                "E5",
            ],
            "auto_apply": False,
            "pilot_genome_ids": list(PILOT_GENOME_IDS),
        },
    }


def list_evolution_goals() -> List[Dict[str, Any]]:
    """列出五域机读目标规格（只读）。

    Returns:
        goal 规格列表（含 non_goals / auto_apply=false）。
    """
    specs = _goal_specs()
    return [dict(specs[gid]) for gid in GOAL_IDS]


def get_evolution_goal(goal_id: str) -> Optional[Dict[str, Any]]:
    """按 id 取目标规格。

    Args:
        goal_id: 如 consultant.sft_quality.v1。
    """
    gid = (goal_id or "").strip()
    specs = _goal_specs()
    row = specs.get(gid)
    return dict(row) if row else None


def measure_curated_feedback_rate() -> Dict[str, Any]:
    """统计轨迹策展好评率 good/(good+bad)。

    Returns:
        good_rate / counts；无样本时 baseline_missing。
    """
    traj_dir = Path(
        os.getenv("AIPLAT_TRAJECTORY_DIR") or get_aiplat_data_dir("trajectories")
    )
    good = 0
    bad = 0
    if traj_dir.is_dir():
        for path in traj_dir.glob("*.jsonl"):
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(row, dict):
                        continue
                    if str(row.get("role") or "") != "assistant":
                        continue
                    q = str(row.get("quality") or "").strip().lower()
                    if q == "good":
                        good += 1
                    elif q == "bad":
                        bad += 1
            except OSError:
                logger.debug("skip traj %s", path, exc_info=True)
                continue
    total = good + bad
    if total <= 0:
        return {
            "ok": True,
            "baseline_missing": True,
            "good_rate": 0.0,
            "good": 0,
            "bad": 0,
            "rated": 0,
        }
    return {
        "ok": True,
        "baseline_missing": False,
        "good_rate": float(good) / float(total),
        "good": good,
        "bad": bad,
        "rated": total,
    }


def _min_sft_samples() -> int:
    try:
        from core.harness.digital_human.consultant_sft_loop import _min_samples

        return int(_min_samples())
    except Exception:
        return 10


def _measure_consultant_sft() -> Dict[str, Any]:
    spec = get_evolution_goal(GOAL_CONSULTANT_SFT) or {}
    thr = float(spec.get("threshold") or CONSULTANT_GOOD_RATE_THRESHOLD)
    rate = measure_curated_feedback_rate()
    min_n = _min_sft_samples()
    rated = int(rate.get("rated") or 0)
    value = float(rate.get("good_rate") or 0.0)
    baseline = bool(rate.get("baseline_missing"))
    meets = (not baseline) and rated >= min_n and value >= thr
    out = {
        "ok": True,
        "goal_id": GOAL_CONSULTANT_SFT,
        "value": value,
        "meets": meets,
        "threshold": thr,
        "baseline_missing": baseline,
        "evidence": {
            "good": rate.get("good"),
            "bad": rate.get("bad"),
            "rated": rated,
            "min_samples": min_n,
        },
        **_base_honesty(),
    }
    return out


def _measure_eval_coverage() -> Dict[str, Any]:
    from core.harness.digital_human.domain_evolution_bridge import load_inventory_file
    from core.harness.evo_compute.coverage import (
        EVAL_THRESHOLD,
        measure_eval_coverage_from_inventory,
    )

    inv = load_inventory_file("eval_inventory") or {}
    m = measure_eval_coverage_from_inventory(
        covered_ids=inv.get("covered_ids"),
        required_ids=inv.get("required_ids"),
    )
    value = float(m.get("coverage") or 0.0)
    thr = float(m.get("threshold") or EVAL_THRESHOLD)
    meets = bool(m.get("meets_g2_threshold")) and not bool(m.get("baseline_missing"))
    return {
        "ok": True,
        "goal_id": GOAL_EVAL_COVERAGE,
        "value": value,
        "meets": meets,
        "threshold": thr,
        "baseline_missing": bool(m.get("baseline_missing")),
        "evidence": {
            "missing_ids": list(m.get("missing_ids") or [])[:30],
            "source": m.get("source") or inv.get("source"),
        },
        **_base_honesty(),
    }


def _measure_fde_evidence() -> Dict[str, Any]:
    from core.harness.digital_human.domain_evolution_bridge import (
        build_fde_inventory_from_delivery_plans,
        load_inventory_file,
    )
    from core.harness.evo_compute.coverage import (
        FDE_THRESHOLD,
        measure_fde_evidence_coverage_from_inventory,
    )

    inv = load_inventory_file("fde_inventory")
    if not inv or not inv.get("required_ids"):
        built = build_fde_inventory_from_delivery_plans()
        if built.get("ok") and built.get("required_ids"):
            inv = built
        else:
            inv = inv or {}
    m = measure_fde_evidence_coverage_from_inventory(
        covered_ids=(inv or {}).get("covered_ids"),
        required_ids=(inv or {}).get("required_ids"),
    )
    value = float(m.get("coverage") or 0.0)
    thr = float(m.get("threshold") or FDE_THRESHOLD)
    meets = bool(m.get("meets_g2_threshold")) and not bool(m.get("baseline_missing"))
    return {
        "ok": True,
        "goal_id": GOAL_FDE_EVIDENCE,
        "value": value,
        "meets": meets,
        "threshold": thr,
        "baseline_missing": bool(m.get("baseline_missing")),
        "evidence": {
            "missing_ids": list(m.get("missing_ids") or [])[:30],
            "plan_count": (inv or {}).get("plan_count"),
            "source": (inv or {}).get("source") or m.get("source"),
        },
        **_base_honesty(),
    }


def _measure_knowledge_fitness() -> Dict[str, Any]:
    from core.harness.digital_human.domain_evolution_bridge import (
        collect_live_knowledge_cases,
    )
    from core.harness.digital_human.evolution_proposals import (
        STATUS_HUMAN_GATE,
        list_evolution_proposals,
    )

    cases = collect_live_knowledge_cases(min_reward=0.0, limit=50)
    emas = [float(c.get("reward_ema") or 0.0) for c in cases if isinstance(c, dict)]
    if not emas:
        value = 0.0
        baseline = True
    else:
        value = sum(emas) / float(len(emas))
        baseline = False
    pending = list_evolution_proposals(kind="knowledge_evolve", status=STATUS_HUMAN_GATE, limit=100)
    backlog = len(pending)
    backlog_alert = backlog > KNOWLEDGE_PENDING_BACKLOG_MAX
    thr = KNOWLEDGE_FITNESS_THRESHOLD
    meets = (not baseline) and value >= thr and not backlog_alert
    return {
        "ok": True,
        "goal_id": GOAL_KNOWLEDGE_FITNESS,
        "value": value,
        "meets": meets,
        "threshold": thr,
        "baseline_missing": baseline,
        "evidence": {
            "n_cases": len(emas),
            "pending_knowledge_evolve": backlog,
            "backlog_alert": backlog_alert,
            "backlog_max": KNOWLEDGE_PENDING_BACKLOG_MAX,
        },
        **_base_honesty(),
    }


def _measure_evo_pilot() -> Dict[str, Any]:
    from core.harness.digital_human.evolution_proposals import (
        STATUS_APPLIED,
        STATUS_APPROVED,
        STATUS_HUMAN_GATE,
        list_evolution_proposals,
    )
    from core.harness.evo_compute.pilots import PILOT_GENOME_IDS

    ready: Dict[str, str] = {}
    for row in list_evolution_proposals(kind="pilot_config", limit=200):
        pl = row.get("payload") or {}
        gid = str(pl.get("genome_id") or "").strip()
        st = str(row.get("status") or "")
        if gid not in PILOT_GENOME_IDS:
            continue
        if st not in (STATUS_HUMAN_GATE, STATUS_APPROVED, STATUS_APPLIED):
            continue
        # 保留最高进度状态
        prev = ready.get(gid)
        rank = {STATUS_HUMAN_GATE: 1, STATUS_APPROVED: 2, STATUS_APPLIED: 3}
        if prev is None or rank.get(st, 0) >= rank.get(prev, 0):
            ready[gid] = st

    n = len(PILOT_GENOME_IDS)
    n_ready = sum(1 for g in PILOT_GENOME_IDS if g in ready)
    value = float(n_ready) / float(n) if n else 0.0
    meets = n_ready >= n and n > 0
    # 沙箱 canary 回执（可选旁证，不阻断 meets）
    canary_path = Path(get_aiplat_home()) / "evolution" / "canary_receipts.jsonl"
    canary_exists = canary_path.is_file()
    return {
        "ok": True,
        "goal_id": GOAL_EVO_PILOT,
        "value": value,
        "meets": meets,
        "threshold": 1.0,
        "baseline_missing": n_ready == 0,
        "evidence": {
            "ready": dict(ready),
            "missing": [g for g in PILOT_GENOME_IDS if g not in ready],
            "canary_receipts_present": canary_exists,
            "note": "ready≠production optimal; sandbox only",
        },
        **_base_honesty(),
    }


_MEASURE_FN = {
    GOAL_CONSULTANT_SFT: _measure_consultant_sft,
    GOAL_EVAL_COVERAGE: _measure_eval_coverage,
    GOAL_FDE_EVIDENCE: _measure_fde_evidence,
    GOAL_KNOWLEDGE_FITNESS: _measure_knowledge_fitness,
    GOAL_EVO_PILOT: _measure_evo_pilot,
}


def measure_evolution_goal(goal_id: str) -> Dict[str, Any]:
    """测量单域目标进度。

    Args:
        goal_id: 五域之一。

    Returns:
        value/meets/evidence + 诚实锁字段；未知 id 时 ok=false。
    """
    gid = (goal_id or "").strip()
    fn = _MEASURE_FN.get(gid)
    if not fn:
        return {
            "ok": False,
            "goal_id": gid,
            "reason": "unknown_goal_id",
            "meets": False,
            **_base_honesty(),
        }
    try:
        row = fn()
        row["measured_at"] = int(time.time())
        return row
    except Exception as e:
        logger.debug("measure %s failed", gid, exc_info=True)
        return {
            "ok": False,
            "goal_id": gid,
            "reason": f"measure_failed:{e}",
            "value": 0.0,
            "meets": False,
            **_base_honesty(),
        }


def measure_all_evolution_goals() -> Dict[str, Any]:
    """测量全部五域目标。

    Returns:
        goals 列表 + 汇总 meets_count；e5_claimed 恒 false。
    """
    rows = [measure_evolution_goal(gid) for gid in GOAL_IDS]
    meets_n = sum(1 for r in rows if r.get("meets"))
    return {
        "ok": True,
        "goals": rows,
        "meets_count": meets_n,
        "total": len(rows),
        **_base_honesty(),
    }


def evolution_goals_brief_line() -> str:
    """简报一行：五域目标进度。"""
    try:
        snap = measure_all_evolution_goals()
        rows = snap.get("goals") or []
        bits: List[str] = []
        for r in rows:
            gid = str(r.get("goal_id") or "").split(".")[0][:6]
            if r.get("baseline_missing"):
                bits.append(f"{gid}:缺测")
            elif r.get("meets"):
                bits.append(f"{gid}:达")
            else:
                v = r.get("value")
                try:
                    bits.append(f"{gid}:{float(v):.0%}")
                except (TypeError, ValueError):
                    bits.append(f"{gid}:?")
        body = " ".join(bits) if bits else "(无)"
        return (
            f"五域进化目标: {snap.get('meets_count', 0)}/{snap.get('total', 0)} 达 "
            f"({body})；非 E5"
        )
    except Exception:
        logger.debug("evolution goals brief failed", exc_info=True)
        return "五域进化目标: (简报未见)"


def goal_progress_for_kind(kind: str) -> Dict[str, Any]:
    """提案 kind → 对应 goal 进度快照（写入 payload）。

    Args:
        kind: evolution proposal kind。
    """
    mapping = {
        "sft_promote": GOAL_CONSULTANT_SFT,
        "purpose_bind": GOAL_CONSULTANT_SFT,
        "eval_coverage": GOAL_EVAL_COVERAGE,
        "fde_evolve": GOAL_FDE_EVIDENCE,
        "knowledge_evolve": GOAL_KNOWLEDGE_FITNESS,
        "pilot_config": GOAL_EVO_PILOT,
    }
    gid = mapping.get((kind or "").strip())
    if not gid:
        return {"goal_id": None, "attached": False}
    prog = measure_evolution_goal(gid)
    return {
        "goal_id": gid,
        "attached": True,
        "value": prog.get("value"),
        "meets": prog.get("meets"),
        "threshold": prog.get("threshold"),
        "baseline_missing": prog.get("baseline_missing"),
        "e5_claimed": False,
    }
