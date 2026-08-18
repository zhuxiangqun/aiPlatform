"""
Skill 路由（候选生成/可解释打分）

用途：
- 为“技能选择/候选解释/回放调参”提供一个可复用的实现
- 目前主要用于：
  1) 在 sys_skill_call 侧记录 candidates 事件（可观测）
  2) 后续可扩展为：路由器/策略器/离线评估器
"""

from __future__ import annotations
import logging

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set
import re


@dataclass(frozen=True)
class SkillCandidate:
    skill_id: str
    name: str
    scope: str  # engine | workspace | unknown
    score: float
    overlap: List[str]


def extract_query_text(params: Dict[str, Any]) -> str:
    """best-effort：从参数中提取“用户问题/指令”文本。"""
    p = params or {}
    for k in ("prompt", "query", "text", "input", "question", "instruction"):
        v = p.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    for _, v in p.items():
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def tokenize(text: str) -> Set[str]:
    """轻量分词：英文按空格；中文做 bigram（best-effort）。"""
    s0 = _norm(text)
    if not s0:
        return set()
    toks: Set[str] = set()
    for w in s0.split():
        if len(w) >= 2:
            toks.add(w)
    for seg in re.findall(r"[\u4e00-\u9fff]{2,}", s0):
        for i in range(0, max(0, len(seg) - 1)):
            toks.add(seg[i : i + 2])
    return toks


def compute_skill_candidates(
    *,
    query_text: str,
    skills: Sequence[Dict[str, Any]],
    top_k: int = 8,
) -> List[SkillCandidate]:
    """
    基于 query_text 与 skill 的 (name/description/trigger_conditions/keywords) overlap 生成候选列表。
    注意：这不是“最终选择”，只是用于可解释的观测与调参。
    """
    qt = tokenize(query_text)
    if not qt:
        return []

    out: List[SkillCandidate] = []
    for s in skills or []:
        try:
            sid = str(s.get("skill_id") or s.get("id") or "").strip()
            name = str(s.get("name") or "").strip()
            scope = str(s.get("scope") or "unknown").strip().lower() or "unknown"
            desc = str(s.get("description") or "").strip()
            tc = s.get("trigger_conditions") or s.get("trigger_keywords") or []
            kw = s.get("keywords") if isinstance(s.get("keywords"), dict) else {}

            tc_s = " ".join([str(x) for x in (tc or [])])
            kw_s = " ".join(
                [str(x) for x in (kw.get("objects") or [])]
                + [str(x) for x in (kw.get("actions") or [])]
                + [str(x) for x in (kw.get("constraints") or [])]
            )
            blob = " ".join([name, desc, tc_s, kw_s]).strip()
            st = tokenize(blob)
            inter = qt & st
            if not inter:
                continue

            score = float(len(inter))
            # 触发短语精确包含加权（轻量）
            for t in (tc or [])[:10]:
                tt = str(t or "").strip()
                if tt and tt in query_text:
                    score += 3.0
                    break

            out.append(
                SkillCandidate(
                    skill_id=sid or name,
                    name=name or sid,
                    scope=scope,
                    score=score,
                    overlap=sorted(list(inter))[:12],
                )
            )
        except Exception:
            continue

    out.sort(key=lambda x: float(x.score), reverse=True)
    return out[: max(1, int(top_k or 8))]


def _norm(s: str) -> str:
    s0 = str(s or "").lower().strip()
    s0 = re.sub(r"[\s\-\._/]+", " ", s0)
    s0 = re.sub(r"[^\w\u4e00-\u9fff ]+", "", s0)
    return s0.strip()


# ── Routing weight learning (P1: feedback loop) ──
# Default weight = 1.0 (neutral). Higher = skill should be preferred.
# Adjusted by apply_learned_weights() based on strict_eval metrics.
# Bounded by _MAX_SKILL_WEIGHTS: skill names come from the registry (bounded),
# but the cap also guards against arbitrary keys from callers.
_MAX_SKILL_WEIGHTS = 512

_skill_weights: Dict[str, float] = {}


def _bounded_weight_write(skill_name: str, weight: float) -> None:
    _skill_weights[skill_name] = weight
    if len(_skill_weights) > _MAX_SKILL_WEIGHTS:
        for name in sorted(_skill_weights)[: len(_skill_weights) - _MAX_SKILL_WEIGHTS]:
            _skill_weights.pop(name, None)


def get_skill_weight(skill_name: str) -> float:
    """Get the learned routing weight for a skill. Default 1.0."""
    return _skill_weights.get(skill_name, 1.0)


def set_skill_weight(skill_name: str, weight: float) -> None:
    """Set the learned routing weight for a skill. Clamped to [0.1, 5.0]."""
    _bounded_weight_write(skill_name, max(0.1, min(5.0, weight)))


def apply_learned_weights() -> Dict[str, Any]:
    """
    Analyze routing strict_eval events and adjust per-skill routing weights.
    
    Logic:
    - For each skill, compute hit_rate = hits / (hits + misroutes + misses)
    - If hit_rate >= 0.80: boost weight slightly (+5% per call)
    - If hit_rate < 0.50: reduce weight (-10% per call)
    - Otherwise: gradually drift toward 1.0 (neutral)
    - Weights are clamped to [0.1, 5.0]
    
    Returns summary dict for observability.
    """
    try:
        from core.services.execution_store import get_execution_store
        store = get_execution_store()
        # Query strict_eval events from last 7 days
        import time
        cutoff = time.time() - 7 * 86400
        
        # Use sync SQLite query to avoid async complexity
        db_path = getattr(getattr(store, '_config', None), 'db_path', None)
        if not db_path:
            return {"applied": False, "reason": "no_db_path"}
        
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        rows = conn.execute(
            "SELECT args_json FROM syscall_events"
            " WHERE kind='routing' AND name='routing_strict_eval'"
            " AND created_at > ?"
            " AND args_json IS NOT NULL",
            (cutoff,)
        ).fetchall()
        conn.close()
        
        if not rows:
            return {"applied": True, "message": "no_strict_eval_events", "weights": dict(_skill_weights)}
        
        # Aggregate per-skill outcomes
        import json
        stats: Dict[str, Dict[str, int]] = {}
        for row in rows:
            try:
                args = json.loads(row["args_json"])
                sname = str(args.get("selected_name") or "")
                outcome = str(args.get("strict_outcome") or "")
                top1 = str(args.get("eligible_top1") or "")
                
                if sname and sname not in stats:
                    stats[sname] = {"hits": 0, "misses": 0, "misroutes": 0}
                if top1 and top1 not in stats:
                    stats[top1] = {"hits": 0, "misses": 0, "misroutes": 0}
                
                if outcome == "hit" and sname:
                    stats[sname]["hits"] = stats.get(sname, {}).get("hits", 0) + 1
                elif outcome == "misroute" and sname:
                    stats[sname]["misroutes"] = stats.get(sname, {}).get("misroutes", 0) + 1
                elif outcome == "miss_tool" and top1:
                    stats[top1]["misses"] = stats.get(top1, {}).get("misses", 0) + 1
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        
        # Adjust weights based on hit_rate
        adjusted: Dict[str, float] = {}
        for sname, st in stats.items():
            total = st.get("hits", 0) + st.get("misroutes", 0) + st.get("misses", 0)
            if total < 3:
                continue  # not enough data
            
            hit_rate = st.get("hits", 0) / max(1, total)
            current = get_skill_weight(sname)
            
            if hit_rate >= 0.80:
                # Boost: add proportional bonus, capped at +10% per round
                new_weight = min(5.0, current + (hit_rate - 0.80) * 0.25)
            elif hit_rate < 0.50:
                # Reduce: stronger penalty for very poor skills
                new_weight = max(0.1, current - (0.50 - hit_rate) * 0.5)
            else:
                # Middle ground: drift toward 1.0
                drift = (1.0 - current) * 0.1
                new_weight = current + drift
            
            new_weight = round(new_weight, 2)
            if abs(new_weight - current) > 0.01:
                set_skill_weight(sname, new_weight)
                adjusted[sname] = new_weight
        
        return {
            "applied": True,
            "adjusted": adjusted,
            "total_skills_analyzed": len(stats),
            "weights": dict(_skill_weights),
        }
    except Exception as e:
        return {"applied": False, "reason": str(e)}


def get_all_weights() -> Dict[str, float]:
    """Get all learned routing weights (copy)."""
    return dict(_skill_weights)


# ═══════════════════════════════════════════════════════════════
# SECI I→S: Canary feedback → KnowledgeAtom (Phase 3)
# ═══════════════════════════════════════════════════════════════

def report_canary_to_seci(
    skill_name: str,
    success: bool,
    *,
    metrics: Dict[str, Any] = None,
    user_feedback: str = "",
) -> Dict[str, Any]:
    """Feed Canary execution results into the SECI knowledge cycle.

    Called after a Canary/A-B test completes. Writes a KnowledgeAtom
    so future executions benefit from the outcome.

    Args:
        skill_name: the skill being tested
        success: whether the Canary test passed
        metrics: optional performance metrics
        user_feedback: optional user-provided feedback text

    Returns:
        {atom_id, success, error (if any)}
    """
    try:
        from core.harness.knowledge.seci_engine import get_seci_engine
        engine = get_seci_engine()
        result = engine.internal_to_socialize(
            skill_name,
            canary_result={
                "success": success,
                "metrics": metrics or {},
                "user_feedback": user_feedback,
            },
        )
        return {"atom_id": result.get("atom_id", ""), "success": True}
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(
            "SECI I→S: Canary report failed for skill '%s': %s", skill_name, str(e)
        )
        return {"atom_id": "", "success": False, "error": str(e)[:200]}

