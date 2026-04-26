"""
Skill 路由（候选生成/可解释打分）

用途：
- 为“技能选择/候选解释/回放调参”提供一个可复用的实现
- 目前主要用于：
  1) 在 sys_skill_call 侧记录 candidates 事件（可观测）
  2) 后续可扩展为：路由器/策略器/离线评估器
"""

from __future__ import annotations

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

