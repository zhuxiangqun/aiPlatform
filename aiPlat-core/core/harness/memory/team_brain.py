"""Team Brain — Hivemind-style shared solutions across agents (thin aggregator).

Does NOT add a parallel memory store. Aggregates:
  - hot TaskSkills (~/.aiplat/task_skills)
  - shared_memory learnings
  - promoted experience_feedback JSON (path-only; no platform import)

publish_* → shared_memory (team-visible)
recall_*  → ranked list for Auto-Recall injection / API
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


@dataclass
class TeamSolution:
    id: str
    kind: str  # task_skill | shared_learning | experience
    title: str
    summary: str
    source: str = ""
    confidence: float = 0.8
    keywords: List[str] = field(default_factory=list)
    created_at: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _tokenize(text: str) -> set:
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1}


def _score(query_tokens: set, blob: str) -> float:
    if not query_tokens:
        return 0.0
    st = _tokenize(blob)
    if not st:
        return 0.0
    return float(len(query_tokens & st)) / float(len(query_tokens))


def _experience_path() -> Path:
    env = os.environ.get("AIPLAT_EXPERIENCE_FILE")
    if env:
        return Path(env)
    home = os.environ.get("AIPLAT_HOME") or str(Path.home() / ".aiplat")
    return Path(home) / "experience_feedback.json"


def _task_skills_dir() -> Path:
    return Path(os.path.expanduser("~/.aiplat/task_skills"))


def publish_task_skill_solution(
    skill: Any,
    *,
    source_agent: str = "",
    source_session: str = "",
) -> Optional[Dict[str, Any]]:
    """Publish a hot TaskSkill into shared_memory for team Auto-Recall."""
    try:
        skill_id = str(getattr(skill, "skill_id", None) or skill.get("skill_id") or "")
        name = str(getattr(skill, "name", None) or (skill.get("name") if isinstance(skill, dict) else "") or skill_id)
        pass_rate = float(getattr(skill, "pass_rate", None) or (skill.get("pass_rate") if isinstance(skill, dict) else 0) or 0)
        keywords = list(getattr(skill, "keywords", None) or (skill.get("keywords") if isinstance(skill, dict) else []) or [])
        if pass_rate < 0.85:
            return None
        summary = (
            f"pipeline={getattr(skill, 'pipeline_id', None) or (skill.get('pipeline_id') if isinstance(skill, dict) else '')}; "
            f"pass_rate={pass_rate:.0%}; agents={getattr(skill, 'agent_sequence', None) or []}; "
            f"keywords={','.join(keywords[:8])}"
        )
        from core.harness.memory.shared_memory import record_learning

        learning = record_learning(
            key=f"team_solution:task_skill:{skill_id}",
            value=summary[:500],
            source_agent=source_agent or name,
            source_session=source_session,
            confidence="high",
        )
        return learning.to_dict() if hasattr(learning, "to_dict") else {"key": f"team_solution:task_skill:{skill_id}"}
    except Exception as e:
        logger.debug("publish_task_skill_solution failed: %s", e, exc_info=True)
        return None


def publish_manual_solution(
    title: str,
    summary: str,
    *,
    source_agent: str = "",
    keywords: Optional[Sequence[str]] = None,
    confidence: str = "high",
) -> Dict[str, Any]:
    """Manual team solution (ops / senior engineer tip)."""
    from core.harness.memory.shared_memory import record_learning

    slug = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff]+", "_", title)[:80]
    key = f"team_solution:manual:{slug}"
    value = summary
    if keywords:
        value = f"{summary} | kw={','.join(list(keywords)[:12])}"
    learning = record_learning(
        key=key,
        value=value[:800],
        source_agent=source_agent or "manual",
        confidence=confidence,
    )
    return learning.to_dict()


def _load_task_skill_solutions(limit: int = 40) -> List[TeamSolution]:
    out: List[TeamSolution] = []
    root = _task_skills_dir()
    if not root.is_dir():
        return out
    for path in sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        pr = float(data.get("pass_rate") or 0)
        if pr < 0.85:
            continue
        kws = [str(x) for x in (data.get("keywords") or [])]
        out.append(
            TeamSolution(
                id=str(data.get("skill_id") or path.stem),
                kind="task_skill",
                title=str(data.get("name") or data.get("skill_id") or path.stem),
                summary=(
                    f"pass_rate={pr:.0%}; pipeline={data.get('pipeline_id', '')}; "
                    f"agents={data.get('agent_sequence') or []}"
                )[:400],
                source=str(data.get("pipeline_id") or "task_skill"),
                confidence=min(1.0, pr),
                keywords=kws,
                created_at=str(data.get("created_at") or ""),
                meta={"path": str(path)},
            )
        )
    return out


def _load_shared_learning_solutions(limit: int = 40) -> List[TeamSolution]:
    out: List[TeamSolution] = []
    try:
        from core.harness.memory.shared_memory import _load_all  # noqa: PLC2701 — aggregator needs store

        rank = {"high": 1.0, "medium": 0.7, "low": 0.4}
        for e in _load_all()[:limit]:
            key = str(getattr(e, "key", "") or "")
            if not key.startswith("team_solution:") and "team_solution" not in key:
                # Still include high-confidence collective learnings for team brain
                if getattr(e, "confidence", "") != "high":
                    continue
            out.append(
                TeamSolution(
                    id=key or f"learning-{len(out)}",
                    kind="shared_learning",
                    title=key.replace("team_solution:", "")[:120] or "shared_learning",
                    summary=str(getattr(e, "value", ""))[:400],
                    source=str(getattr(e, "source_agent", "") or "shared_memory"),
                    confidence=rank.get(str(getattr(e, "confidence", "medium")), 0.7),
                    keywords=list(_tokenize(f"{key} {getattr(e, 'value', '')}"))[:12],
                    created_at=str(getattr(e, "timestamp", "") or ""),
                )
            )
    except Exception as e:
        logger.debug("shared learning load failed: %s", e, exc_info=True)
    return out


def _load_experience_solutions(limit: int = 40) -> List[TeamSolution]:
    out: List[TeamSolution] = []
    path = _experience_path()
    if not path.is_file():
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        records = data if isinstance(data, list) else []
    except Exception:
        return out
    for rec in records:
        status = str(rec.get("status") or "")
        if not status.startswith("promoted"):
            continue
        if status.endswith(":review"):
            continue  # high-risk awaiting human confirm
        rid = str(rec.get("rule_id") or rec.get("id") or "")
        content = str(rec.get("content") or rec.get("promote_draft") or "")
        out.append(
            TeamSolution(
                id=rid or f"exp-{len(out)}",
                kind="experience",
                title=rid or "experience",
                summary=content[:400],
                source=str(rec.get("source") or "experience_feedback"),
                confidence=float(rec.get("confidence") or 0.9),
                keywords=list(_tokenize(f"{rid} {content}"))[:12],
                created_at=str(rec.get("promoted_at") or rec.get("updated_at") or ""),
            )
        )
        if len(out) >= limit:
            break
    return out


def list_team_solutions(limit: int = 30) -> List[TeamSolution]:
    """Union of team-visible solutions (no query ranking)."""
    items = _load_task_skill_solutions() + _load_shared_learning_solutions() + _load_experience_solutions()
    # de-dupe by id+kind
    seen = set()
    uniq: List[TeamSolution] = []
    for it in items:
        k = (it.kind, it.id)
        if k in seen:
            continue
        seen.add(k)
        uniq.append(it)
    uniq.sort(key=lambda x: (x.confidence, x.created_at), reverse=True)
    return uniq[:limit]


def recall_team_solutions(
    query: str = "",
    *,
    limit: int = 8,
    min_score: float = 0.15,
) -> List[TeamSolution]:
    """Auto-Recall: rank team solutions by keyword overlap with query."""
    items = list_team_solutions(limit=80)
    qt = _tokenize(query)
    if not qt:
        return items[:limit]
    scored: List[tuple] = []
    for it in items:
        blob = f"{it.title} {it.summary} {' '.join(it.keywords)}"
        s = _score(qt, blob) + 0.1 * float(it.confidence)
        if s >= min_score:
            scored.append((s, it))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in scored[:limit]]


def format_recall_message(items: Sequence[TeamSolution]) -> Optional[Dict[str, Any]]:
    """Build a system message for MemoryManager.build_context injection."""
    if not items:
        return None
    lines = [
        "[Team Brain] Shared solutions from other agents/sessions — reuse before re-deriving:",
    ]
    for it in items:
        lines.append(
            f"- ({it.kind}) {it.title}: {it.summary[:180]} "
            f"[source={it.source or 'team'}, conf={it.confidence:.0%}]"
        )
    lines.append("→ Prefer sys_skill_call / existing patterns when a match is relevant.")
    return {
        "role": "system",
        "content": "\n".join(lines),
        "meta": {
            "role": "team_brain_recall",
            "count": len(items),
            "ids": [it.id for it in items],
            "kinds": [it.kind for it in items],
        },
    }


def team_brain_status() -> Dict[str, Any]:
    items = list_team_solutions(limit=200)
    by_kind: Dict[str, int] = {}
    for it in items:
        by_kind[it.kind] = by_kind.get(it.kind, 0) + 1
    return {
        "total": len(items),
        "by_kind": by_kind,
        "task_skills_dir": str(_task_skills_dir()),
        "experience_path": str(_experience_path()),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
