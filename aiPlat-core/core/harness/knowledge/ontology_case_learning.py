"""Ontology online learning (P0) + gated self-evolution (P1/P2).

P0: case library + feedback → reward-weighted / optional UCB retrieval (no policy RL).
P1: high-reward cases → VersionedOntologyStore draft proposals (default never auto-apply).
P2: opt-in edge auto apply + rollback; ContextBus overlay injects cases (does not mutate TBox).

Authority: live TBox stays YAML; this module never writes ontology YAML directly.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CLASS_HINT = re.compile(
    r"(?:class|entity|表|实体|缺口|缺失)\s*[:=]?\s*[`\"']?"
    r"([A-Za-z_][\w]{2,64}|[\u4e00-\u9fff]{2,32})",
    re.IGNORECASE,
)
_TOKEN = re.compile(r"[a-zA-Z一-鿿]{2,}")


def _enabled() -> bool:
    return os.getenv("AIPLAT_ONTOLOGY_CASE_LEARNING", "true").lower() not in (
        "0",
        "false",
        "no",
    )


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")))


def _cases_dir() -> Path:
    d = _home() / "ontology_cases"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _domain_path(domain_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (domain_id or "default"))
    return _cases_dir() / f"{safe}.json"


def _cold_path(domain_id: str) -> Path:
    d = _cases_dir() / "cold"
    d.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (domain_id or "default"))
    return d / f"{safe}.json"


def _evolve_min_reward() -> float:
    try:
        return float(os.getenv("AIPLAT_ONTOLOGY_EVOLVE_MIN_REWARD", "0.7"))
    except ValueError:
        return 0.7


def _evolve_min_feedback() -> int:
    try:
        return int(os.getenv("AIPLAT_ONTOLOGY_EVOLVE_MIN_FEEDBACK", "1"))
    except ValueError:
        return 1


def _edge_auto_apply_enabled() -> bool:
    """Default OFF. When true, edge-only drafts may approve→apply (still rollbackable)."""
    return os.getenv("AIPLAT_ONTOLOGY_EDGE_AUTO_APPLY", "false").lower() in (
        "1",
        "true",
        "yes",
    )


def _ucb_enabled() -> bool:
    return os.getenv("AIPLAT_ONTOLOGY_CASE_UCB", "true").lower() not in (
        "0",
        "false",
        "no",
    )


def _ucb_c() -> float:
    try:
        return float(os.getenv("AIPLAT_ONTOLOGY_CASE_UCB_C", "0.35"))
    except ValueError:
        return 0.35


@dataclass
class OntologyCase:
    case_id: str
    domain_id: str
    title: str
    summary: str
    outcome: str = "success"  # success | failure | partial
    reward: float = 0.5
    reward_ema: float = 0.5
    feedback_count: int = 0
    serve_count: int = 0  # P2.5: retrieval impressions for UCB
    action_id: str = ""
    entity_id: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    proposal_id: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "OntologyCase":
        return cls(
            case_id=str(raw.get("case_id") or ""),
            domain_id=str(raw.get("domain_id") or "default"),
            title=str(raw.get("title") or "")[:200],
            summary=str(raw.get("summary") or "")[:4000],
            outcome=str(raw.get("outcome") or "success"),
            reward=float(raw.get("reward") or 0.5),
            reward_ema=float(raw.get("reward_ema") if raw.get("reward_ema") is not None else raw.get("reward") or 0.5),
            feedback_count=int(raw.get("feedback_count") or 0),
            serve_count=int(raw.get("serve_count") or 0),
            action_id=str(raw.get("action_id") or ""),
            entity_id=str(raw.get("entity_id") or ""),
            tags=list(raw.get("tags") or []),
            metadata=dict(raw.get("metadata") or {}),
            proposal_id=str(raw.get("proposal_id") or ""),
            created_at=float(raw.get("created_at") or time.time()),
            updated_at=float(raw.get("updated_at") or time.time()),
        )


class OntologyCaseStore:
    """Per-domain JSON case library with reward-weighted keyword retrieval."""

    def __init__(self, domain_id: str = ""):
        self.domain_id = (domain_id or "").strip() or "default"

    def _load(self) -> Dict[str, OntologyCase]:
        path = _domain_path(self.domain_id)
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            items = data.get("cases") if isinstance(data, dict) else data
            out: Dict[str, OntologyCase] = {}
            for row in items or []:
                if not isinstance(row, dict):
                    continue
                c = OntologyCase.from_dict(row)
                if c.case_id:
                    out[c.case_id] = c
            return out
        except Exception:
            logger.warning("ontology case load failed: %s", path, exc_info=True)
            return {}

    def _save(self, cases: Dict[str, OntologyCase]) -> None:
        path = _domain_path(self.domain_id)
        payload = {
            "domain_id": self.domain_id,
            "updated_at": time.time(),
            "cases": [c.to_dict() for c in cases.values()],
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def record(
        self,
        *,
        title: str,
        summary: str,
        outcome: str = "success",
        reward: Optional[float] = None,
        action_id: str = "",
        entity_id: str = "",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        case_id: str = "",
        write_graph: bool = False,
    ) -> Dict[str, Any]:
        if not _enabled():
            return {"status": "disabled", "case_id": ""}

        outcome_n = (outcome or "success").strip().lower()
        if reward is None:
            reward = {"success": 0.8, "partial": 0.5, "failure": 0.2}.get(outcome_n, 0.5)
        reward = max(0.0, min(1.0, float(reward)))

        cid = (case_id or "").strip() or f"ocase_{uuid.uuid4().hex[:12]}"
        cases = self._load()
        case = OntologyCase(
            case_id=cid,
            domain_id=self.domain_id,
            title=(title or summary or cid)[:200],
            summary=(summary or title or "")[:4000],
            outcome=outcome_n,
            reward=reward,
            reward_ema=reward,
            action_id=action_id or "",
            entity_id=entity_id or "",
            tags=list(tags or []),
            metadata=dict(metadata or {}),
        )
        cases[cid] = case
        # Cap per domain
        if len(cases) > 5000:
            oldest = sorted(cases.values(), key=lambda c: c.created_at)[: len(cases) - 5000]
            for o in oldest:
                cases.pop(o.case_id, None)
        self._save(cases)

        graph_meta: Dict[str, Any] = {}
        if write_graph:
            graph_meta = self._maybe_write_graph(case)

        return {"status": "ok", "case_id": cid, "reward": reward, **graph_meta}

    def _maybe_write_graph(self, case: OntologyCase) -> Dict[str, Any]:
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex

            g = GraphIndex.load(self.domain_id)
            nid = case.case_id
            g.add_entity(nid, case.title[:60] or nid, "case_study")
            g.add_entity_property(nid, "summary", case.summary[:500])
            g.add_entity_property(nid, "reward_ema", case.reward_ema)
            g.add_entity_property(nid, "outcome", case.outcome)
            if case.entity_id and case.entity_id in g._nodes:
                g.add_relation(nid, case.entity_id, "case_study_of")
            g.save()
            return {"graph_entity_id": nid, "write_graph": True}
        except Exception:
            logger.debug("case graph write skipped", exc_info=True)
            return {"write_graph": False}

    def record_feedback(
        self,
        case_id: str,
        *,
        rating: float,
        note: str = "",
        actor: str = "user",
    ) -> Dict[str, Any]:
        if not _enabled():
            return {"status": "disabled"}
        cases = self._load()
        case = cases.get(case_id)
        if not case:
            # try scan all domains
            found = find_case(case_id)
            if not found:
                return {"status": "not_found", "case_id": case_id}
            self.domain_id = found.domain_id
            cases = self._load()
            case = cases.get(case_id)
            if not case:
                return {"status": "not_found", "case_id": case_id}

        rating_n = max(0.0, min(1.0, float(rating)))
        alpha = 0.4
        case.reward_ema = (1 - alpha) * case.reward_ema + alpha * rating_n
        case.reward = rating_n
        case.feedback_count += 1
        case.updated_at = time.time()
        fb = list(case.metadata.get("feedback") or [])
        fb.append(
            {
                "rating": rating_n,
                "note": (note or "")[:500],
                "actor": actor,
                "at": case.updated_at,
            }
        )
        case.metadata["feedback"] = fb[-50:]
        cases[case_id] = case
        self._save(cases)
        return {
            "status": "ok",
            "case_id": case_id,
            "reward_ema": case.reward_ema,
            "feedback_count": case.feedback_count,
        }

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        outcome: str = "",
    ) -> List[Dict[str, Any]]:
        if not _enabled():
            return []
        loaded = self._load()
        cases = list(loaded.values())
        if not cases:
            return []
        q = (query or "").strip().lower()
        q_tokens = set(_TOKEN.findall(q)) if q else set()
        # Total pulls ≈ serves + feedback (bandit clock); not policy-gradient RL
        total_pulls = (
            sum(max(0, int(c.serve_count)) + max(0, int(c.feedback_count)) for c in cases) + 1
        )
        use_ucb = _ucb_enabled()
        c_ucb = _ucb_c()
        scored: List[tuple] = []
        for c in cases:
            if outcome and c.outcome != outcome:
                continue
            text = f"{c.title} {c.summary} {' '.join(c.tags)}".lower()
            t_tokens = set(_TOKEN.findall(text))
            if q_tokens:
                overlap = len(q_tokens & t_tokens) / max(len(q_tokens | t_tokens), 1)
            else:
                overlap = 0.3
            reward = max(0.0, min(1.0, c.reward_ema))
            # P2/P2.5: UCB1 on under-served / under-feedback cases (ranking only)
            bonus = 0.0
            if use_ucb:
                import math

                n_i = max(0, int(c.serve_count)) + max(0, int(c.feedback_count)) + 1
                bonus = c_ucb * math.sqrt(math.log(total_pulls + 1) / n_i)
                score = 0.40 * overlap + 0.35 * reward + 0.25 * min(1.0, bonus)
            else:
                score = 0.55 * overlap + 0.45 * reward
            if score >= 0.12:
                scored.append((score, c, bonus))
        scored.sort(key=lambda x: (-x[0], -x[1].updated_at))
        top = scored[: max(1, top_k)]
        # Impression writeback for next-round UCB (best-effort, same domain file)
        if top:
            dirty = False
            for _score, c, _bonus in top:
                if c.case_id in loaded:
                    loaded[c.case_id].serve_count = int(loaded[c.case_id].serve_count or 0) + 1
                    dirty = True
            if dirty:
                try:
                    self._save(loaded)
                except Exception:
                    logger.debug("case serve_count persist skipped", exc_info=True)
        out: List[Dict[str, Any]] = []
        for score, c, bonus in top:
            fresh = loaded.get(c.case_id) or c
            row = {**fresh.to_dict(), "score": round(score, 4)}
            if use_ucb:
                row["ucb_bonus"] = round(float(bonus), 4)
            out.append(row)
        return out

    def get(self, case_id: str) -> Optional[OntologyCase]:
        return self._load().get(case_id)


def ontology_case_learning_meta(domain_id: str = "") -> Dict[str, Any]:
    """Runtime flags for demos / ops (no secrets). Does not mutate TBox."""
    did = (domain_id or "").strip()
    meta: Dict[str, Any] = {
        "enabled": _enabled(),
        "ucb_enabled": _ucb_enabled(),
        "ucb_c": _ucb_c(),
        "edge_auto_apply_enabled": _edge_auto_apply_enabled(),
        "evolve_min_reward": _evolve_min_reward(),
        "evolve_min_feedback": _evolve_min_feedback(),
        "authority_note": (
            "案例检索可学习排序；默认提案不自动 apply；"
            "仅 AIPLAT_ONTOLOGY_EDGE_AUTO_APPLY 开启时 edge 可自动 apply+回滚；禁升格 logic/core"
        ),
    }
    if did:
        cases = OntologyCaseStore(did)._load()
        meta["domain_id"] = did
        meta["case_count"] = len(cases)
        meta["total_serves"] = sum(int(c.serve_count or 0) for c in cases.values())
        meta["total_feedback"] = sum(int(c.feedback_count or 0) for c in cases.values())
    return meta


def select_cases_for_context(hits: List[Dict[str, Any]], *, top_k: int = 3) -> Dict[str, Any]:
    """Drop repeated low-yield failures from injection. Does not delete cases."""
    cap = max(1, min(int(top_k or 3), 8))
    kept: List[Dict[str, Any]] = []
    demoted = 0
    for row in hits or []:
        if not isinstance(row, dict):
            continue
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        if meta.get("cold_archived"):
            demoted += 1
            continue
        try:
            serves = int(row.get("serve_count") or 0)
        except (TypeError, ValueError):
            serves = 0
        try:
            ema = float(row.get("reward_ema") if row.get("reward_ema") is not None else 1)
        except (TypeError, ValueError):
            ema = 1.0
        outcome = str(row.get("outcome") or "")
        if serves >= 4 and ema < 0.35 and outcome == "failure":
            demoted += 1
            continue
        kept.append(row)
        if len(kept) >= cap:
            break
    return {"kept": kept, "demoted": demoted, "deleted": False}


def is_cold_archive_candidate(case: Any) -> bool:
    """Stricter than inject demotion. Does not mutate."""
    if isinstance(case, dict):
        meta = case.get("metadata") if isinstance(case.get("metadata"), dict) else {}
        serves = int(case.get("serve_count") or 0)
        fb = int(case.get("feedback_count") or 0)
        outcome = str(case.get("outcome") or "")
        try:
            ema = float(case.get("reward_ema") if case.get("reward_ema") is not None else 1)
        except (TypeError, ValueError):
            ema = 1.0
    else:
        meta = case.metadata if isinstance(getattr(case, "metadata", None), dict) else {}
        serves = int(getattr(case, "serve_count", 0) or 0)
        fb = int(getattr(case, "feedback_count", 0) or 0)
        outcome = str(getattr(case, "outcome", "") or "")
        try:
            ema = float(getattr(case, "reward_ema", 1) if getattr(case, "reward_ema", None) is not None else 1)
        except (TypeError, ValueError):
            ema = 1.0
    if meta.get("cold_archived"):
        return False
    if serves >= 8 and ema < 0.35 and outcome == "failure":
        return True
    if serves >= 20 and (fb / serves) < 0.05:
        return True
    return False


def _load_cold(domain_id: str) -> Dict[str, OntologyCase]:
    path = _cold_path(domain_id)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("cases") if isinstance(data, dict) else data
        out: Dict[str, OntologyCase] = {}
        for row in items or []:
            if not isinstance(row, dict):
                continue
            c = OntologyCase.from_dict(row)
            if c.case_id:
                out[c.case_id] = c
        return out
    except Exception:
        logger.warning("cold case load failed: %s", path, exc_info=True)
        return {}


def _save_cold(domain_id: str, cases: Dict[str, OntologyCase]) -> None:
    path = _cold_path(domain_id)
    payload = {
        "domain_id": domain_id,
        "updated_at": time.time(),
        "cases": [c.to_dict() for c in cases.values()],
        "authority_note": "冷库只供审计。不参与 ContextBus 注入。不改 TBox。",
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def list_cold_cases(domain_id: str = "it-ops", *, limit: int = 20) -> Dict[str, Any]:
    """Read-only cold archive listing. Does not inject or write YAML."""
    did = (domain_id or "").strip() or "it-ops"
    lim = max(1, min(int(limit or 20), 50))
    rows = list(_load_cold(did).values())
    rows.sort(key=lambda c: float((c.metadata or {}).get("archived_at") or c.updated_at or 0), reverse=True)
    items = [
        {
            "case_id": c.case_id,
            "title": c.title,
            "outcome": c.outcome,
            "serve_count": c.serve_count,
            "feedback_count": c.feedback_count,
            "reward_ema": c.reward_ema,
            "archived_at": (c.metadata or {}).get("archived_at"),
        }
        for c in rows[:lim]
    ]
    return {
        "ok": True,
        "domain_id": did,
        "items": items,
        "count": len(rows),
        "deleted": False,
        "wrote_live_yaml": False,
        "tbox_changed": False,
        "authority_note": "冷库只读。不参与注入。不是删除。",
    }


def archive_cold_cases(domain_id: str = "it-ops", *, limit: int = 20) -> Dict[str, Any]:
    """Move low-yield live cases to cold store. Does not delete. Does not change TBox."""
    did = (domain_id or "").strip() or "it-ops"
    cap = max(1, min(int(limit or 20), 40))
    store = OntologyCaseStore(did)
    live = store._load()
    cold = _load_cold(did)
    moved: List[Dict[str, Any]] = []
    clock = time.time()
    for case_id, case in list(live.items()):
        if len(moved) >= cap:
            break
        if not is_cold_archive_candidate(case):
            continue
        meta = dict(case.metadata or {})
        meta["cold_archived"] = True
        meta["archived_at"] = clock
        case.metadata = meta
        case.updated_at = clock
        cold[case_id] = case
        del live[case_id]
        moved.append(
            {
                "case_id": case_id,
                "serve_count": case.serve_count,
                "reward_ema": case.reward_ema,
                "outcome": case.outcome,
            }
        )
    if moved:
        store._save(live)
        _save_cold(did, cold)
    return {
        "ok": True,
        "domain_id": did,
        "moved": moved,
        "moved_count": len(moved),
        "cold_count": len(cold),
        "deleted": False,
        "wrote_live_yaml": False,
        "tbox_changed": False,
        "m4_claim_allowed": False,
        "authority_note": "已移入冷库，不再注入。未删除。未改 TBox。",
    }


def context_hit_rate(cases: List[Any]) -> Dict[str, Any]:
    """Injected cases that received feedback. No cases served → no rate."""
    served = 0
    used = 0
    for case in cases or []:
        if isinstance(case, dict):
            serves = int(case.get("serve_count") or 0)
            feedback = int(case.get("feedback_count") or 0)
        else:
            serves = int(getattr(case, "serve_count", 0) or 0)
            feedback = int(getattr(case, "feedback_count", 0) or 0)
        if serves <= 0:
            continue
        served += 1
        if feedback > 0:
            used += 1
    return {
        "served": served,
        "used": used,
        "hit_rate": (used / served) if served else None,
        "wrote_live_yaml": False,
    }


def format_cases_for_context(
    domain_id: str,
    query: str = "",
    *,
    top_k: int = 3,
) -> str:
    """Compact overlay for ContextBus / prompts. Not TBox authority."""
    if not _enabled() or not (domain_id or "").strip():
        return ""
    hits = OntologyCaseStore(domain_id).search(query or domain_id, top_k=max(top_k * 4, top_k))
    picked = select_cases_for_context(hits, top_k=top_k)
    chosen = picked["kept"]
    demoted = int(picked["demoted"] or 0)
    if not chosen:
        if demoted:
            return (
                f"## 本体在线学习案例（{domain_id}；建议层≠说明书）\n"
                f"降权/冷库候选 {demoted} 条反复失败且低收益案例，未删除，本轮不注入。"
            )
        return ""
    lines: List[str] = []
    for h in chosen:
        ema = h.get("reward_ema")
        try:
            ema_s = f"{float(ema):.2f}"
        except (TypeError, ValueError):
            ema_s = str(ema or "—")
        summary = (h.get("summary") or "")[:160].replace("\n", " ")
        lines.append(
            f"- [{h.get('case_id')}] {(h.get('title') or '')[:80]} "
            f"(outcome={h.get('outcome')} ema={ema_s} score={h.get('score')}) {summary}"
        )
    note = f"降权/冷库候选 {demoted} 条，未删除。" if demoted else ""
    return (
        f"## 本体在线学习案例（{domain_id}；奖励加权/UCB；建议层≠说明书）\n"
        + note
        + ("\n" if note else "")
        + "\n".join(lines)
    )


def find_case(case_id: str) -> Optional[OntologyCase]:
    root = _cases_dir()
    if not root.is_dir():
        return None
    for path in root.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for row in data.get("cases") or []:
                if isinstance(row, dict) and row.get("case_id") == case_id:
                    return OntologyCase.from_dict(row)
        except Exception:
            continue
    return None


def _outcome_from_status(status: str) -> str:
    s = (status or "").lower()
    if s in ("executed", "done", "completed", "success", "ok"):
        return "success"
    if s in ("partial", "closure_gated", "pending_approval"):
        return "partial"
    return "failure"


def record_case_from_action(
    *,
    domain_id: str,
    action_id: str,
    entity_id: str,
    status: str,
    result: Any = None,
    actor: str = "",
    write_graph: bool = False,
) -> Dict[str, Any]:
    """Best-effort hook for ActionRegistry — never raises to caller."""
    if not _enabled():
        return {"status": "disabled"}
    try:
        outcome = _outcome_from_status(status)
        snippet = ""
        if isinstance(result, dict):
            snippet = str(result.get("summary") or result.get("message") or result)[:800]
        elif result is not None:
            snippet = str(result)[:800]
        store = OntologyCaseStore(domain_id)
        return store.record(
            title=f"{action_id}@{entity_id or 'entity'}",
            summary=f"action={action_id} entity={entity_id} status={status} actor={actor} {snippet}".strip(),
            outcome=outcome,
            action_id=action_id,
            entity_id=entity_id or "",
            tags=["action_audit", outcome],
            metadata={"actor": actor, "raw_status": status},
            write_graph=write_graph,
        )
    except Exception:
        logger.debug("record_case_from_action failed", exc_info=True)
        return {"status": "error"}


def _suggest_class_names(case: OntologyCase) -> List[str]:
    text = f"{case.title}\n{case.summary}\n{case.metadata.get('gap_hint', '')}"
    found: List[str] = []
    seen = set()
    for m in _CLASS_HINT.finditer(text):
        name = (m.group(1) or "").strip()
        if not name or name.lower() in seen:
            continue
        if name.lower() in {"self", "true", "false", "none", "null", "type", "string", "action"}:
            continue
        seen.add(name.lower())
        found.append(name)
        if len(found) >= 5:
            break
    if not found:
        # deterministic edge suggestion from action id tail
        tail = (case.action_id or "LearnedConcept").split(":")[-1]
        safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in tail)[:48]
        if safe:
            found.append(f"CaseDerived_{safe}"[:64])
    return found


async def maybe_enqueue_evolution_proposal(
    case_id: str,
    *,
    force: bool = False,
    author: str = "ontology-case-learning",
) -> Dict[str, Any]:
    """P1: high-reward case → draft ontology proposal (auto_apply=false)."""
    case = find_case(case_id)
    if not case:
        return {"status": "not_found", "case_id": case_id, "auto_apply": False}

    if case.proposal_id and not force:
        return {
            "status": "already_enqueued",
            "case_id": case_id,
            "proposal_id": case.proposal_id,
            "auto_apply": False,
        }

    if not force:
        if case.reward_ema < _evolve_min_reward():
            return {
                "status": "below_threshold",
                "case_id": case_id,
                "reward_ema": case.reward_ema,
                "min_reward": _evolve_min_reward(),
                "auto_apply": False,
            }
        if case.feedback_count < _evolve_min_feedback() and case.outcome != "success":
            return {
                "status": "need_feedback",
                "case_id": case_id,
                "feedback_count": case.feedback_count,
                "auto_apply": False,
            }

    names = _suggest_class_names(case)
    first = names[0]
    safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in first)[:64] or "LearnedClass"
    changes = {
        "add": {
            "class": {
                "name": safe,
                "label": first,
                "tier": "edge",
                "required_fields": ["name"],
                "description": (
                    f"Suggested from ontology case {case.case_id} "
                    f"(reward_ema={case.reward_ema:.2f}, action={case.action_id})"
                ),
            }
        },
        "source": {
            "kind": "ontology_case_learning",
            "case_id": case.case_id,
            "auto_apply": False,
        },
    }

    proposal_id: Optional[str] = None
    enqueue_status = "draft"
    try:
        from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore

        store = VersionedOntologyStore(case.domain_id)
        proposal_id = await store.create_proposal(changes, author=author)
    except Exception as e:
        logger.warning("enqueue evolution proposal failed", exc_info=True)
        proposal_id = f"draft_local_{case.domain_id}_{safe}_{int(time.time())}"
        enqueue_status = "local_draft"
        changes["enqueue_error"] = type(e).__name__

    # persist proposal_id on case
    oc = OntologyCaseStore(case.domain_id)
    cases = oc._load()
    if case_id in cases:
        cases[case_id].proposal_id = proposal_id or ""
        cases[case_id].updated_at = time.time()
        cases[case_id].metadata["evolution"] = {
            "proposal_id": proposal_id,
            "suggested_class": safe,
            "enqueue_status": enqueue_status,
        }
        oc._save(cases)

    auto_apply = False
    auto_receipt: Dict[str, Any] = {}
    authority = "仅提案草稿；默认禁止自动 apply；须 approve→apply"
    if (
        enqueue_status == "draft"
        and proposal_id
        and _edge_auto_apply_enabled()
        and not str(proposal_id).startswith("draft_local_")
    ):
        try:
            from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore

            auto_receipt = await VersionedOntologyStore(case.domain_id).try_auto_apply_edge_proposal(
                proposal_id, actor=f"case-edge-auto:{author}"
            )
            auto_apply = bool(auto_receipt.get("auto_applied") and auto_receipt.get("ok"))
            if auto_apply:
                enqueue_status = "edge_auto_applied"
                authority = (
                    "edge 自动 apply（AIPLAT_ONTOLOGY_EDGE_AUTO_APPLY）；"
                    "可用 rollback_proposal 回滚；禁升格 logic/core"
                )
                if case_id in cases:
                    cases[case_id].metadata["evolution"] = {
                        **(cases[case_id].metadata.get("evolution") or {}),
                        "enqueue_status": enqueue_status,
                        "auto_apply": True,
                        "apply_receipt": {
                            k: auto_receipt.get(k)
                            for k in (
                                "version_from",
                                "version_to",
                                "rollback_snapshot",
                                "classes_added",
                            )
                        },
                    }
                    oc._save(cases)
            else:
                authority = (
                    f"提案已入队；edge 自动 apply 未执行"
                    f"（{auto_receipt.get('reason') or 'unknown'}）；须人工 approve→apply"
                )
        except Exception:
            logger.warning("edge auto-apply failed", exc_info=True)
            authority = "提案已入队；edge 自动 apply 异常，须人工 approve→apply"

    return {
        "status": enqueue_status,
        "case_id": case_id,
        "domain_id": case.domain_id,
        "proposal_id": proposal_id,
        "suggested_class": safe,
        "suggestions": [
            {
                "kind": "new_class",
                "name": safe,
                "label": first,
                "tier": "edge",
                "apply_path": "proposal",
                "auto_apply": auto_apply,
            }
        ],
        "auto_apply": auto_apply,
        "edge_auto_apply_enabled": _edge_auto_apply_enabled(),
        "apply_receipt": auto_receipt or None,
        "authority_note": authority,
    }


async def rollback_case_evolution(case_id: str) -> Dict[str, Any]:
    """P2: rollback live YAML for the proposal linked to a case (if applied)."""
    case = find_case(case_id)
    if not case:
        return {"ok": False, "reason": "case_not_found", "case_id": case_id}
    proposal_id = (case.proposal_id or "").strip()
    if not proposal_id:
        return {"ok": False, "reason": "no_proposal", "case_id": case_id}
    if proposal_id.startswith("draft_local_") or proposal_id.startswith("k5_local_"):
        return {"ok": False, "reason": "local_draft_not_applied", "case_id": case_id, "proposal_id": proposal_id}
    try:
        from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore

        receipt = await VersionedOntologyStore(case.domain_id).rollback_proposal(proposal_id)
        if receipt.get("ok"):
            oc = OntologyCaseStore(case.domain_id)
            cases = oc._load()
            if case_id in cases:
                evo = dict(cases[case_id].metadata.get("evolution") or {})
                evo["enqueue_status"] = "rolled_back"
                evo["auto_apply"] = False
                evo["rolled_back_at"] = time.time()
                cases[case_id].metadata["evolution"] = evo
                oc._save(cases)
        return {**receipt, "case_id": case_id}
    except Exception as e:
        logger.warning("rollback_case_evolution failed", exc_info=True)
        return {"ok": False, "reason": type(e).__name__, "case_id": case_id, "proposal_id": proposal_id}


async def record_feedback_and_maybe_evolve(
    case_id: str,
    *,
    rating: float,
    note: str = "",
    actor: str = "user",
    auto_enqueue: bool = True,
) -> Dict[str, Any]:
    """Feedback writeback; optionally enqueue proposal when threshold met."""
    case = find_case(case_id)
    if not case:
        return {"status": "not_found", "case_id": case_id}
    store = OntologyCaseStore(case.domain_id)
    fb = store.record_feedback(case_id, rating=rating, note=note, actor=actor)
    evolve: Dict[str, Any] = {"status": "skipped"}
    if auto_enqueue and fb.get("status") == "ok":
        if float(fb.get("reward_ema") or 0) >= _evolve_min_reward():
            evolve = await maybe_enqueue_evolution_proposal(case_id, author=f"feedback:{actor}")
    return {"feedback": fb, "evolve": evolve, "auto_apply": False}
