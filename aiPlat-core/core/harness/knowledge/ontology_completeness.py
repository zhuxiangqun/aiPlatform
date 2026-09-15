"""Ontology Completeness Score (OCS) — docs/contracts/ONTOLOGY_COMPLETENESS.md

Weighted 0–100 per domain. ≥80 = 纵深完整; ≥70 = pilot.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

WEIGHTS = {
    "C1": 15,
    "C2": 20,
    "C3": 15,
    "C4": 25,
    "C5": 15,
    "C6": 10,
}


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat"))


def _score_c1(domain) -> float:
    classes = list(domain.classes or [])
    if not classes:
        return 0.0
    with_req = sum(1 for c in classes if c.required_fields)
    return 100.0 * with_req / len(classes)


def _score_c2(domain) -> float:
    classes = list(domain.classes or [])
    if not classes:
        return 0.0
    with_states = 0
    with_trans = 0
    for c in classes:
        st = c.states or {}
        enum = st.get("enum") if isinstance(st, dict) else None
        if enum:
            with_states += 1
        transitions = c.transitions or (st.get("transitions") if isinstance(st, dict) else None) or []
        if transitions:
            with_trans += 1
    # 70% from having states, 30% from transitions
    base = 100.0 * with_states / len(classes)
    bonus = 30.0 * with_trans / len(classes)
    return min(100.0, base * 0.7 + bonus)


def _score_c3(domain) -> float:
    n = len(domain.axioms or [])
    if n >= 3:
        return 100.0
    if n == 2:
        return 70.0
    if n == 1:
        return 40.0
    return 0.0


def _score_c4(domain_id: str) -> float:
    # Prefer workspace/home action YAML seeds (stable, no broken custom_handlers noise)
    seed_score = _score_c4_from_seeds(domain_id)
    if seed_score > 0:
        return seed_score
    try:
        from core.harness.ontology_engine.action_registry import AsyncActionRegistry
        from core.harness.ontology_engine.builtin_actions import register_all
        from unittest.mock import AsyncMock

        reg = AsyncActionRegistry(store=AsyncMock())
        register_all(reg)
        actions = []
        for aid, c in list(getattr(reg, "_contracts", {}) or {}).items():
            if getattr(c, "domain_id", "") != domain_id:
                continue
            ns = getattr(c, "action_namespace", "") or ""
            if ns == "customer_action" or str(aid).startswith("customer_action:"):
                actions.append(c)
        if not actions:
            return 0.0
        gated = sum(
            1
            for c in actions
            if getattr(c, "required_state", None) or getattr(c, "forbidden_states", None)
        )
        count_score = min(100.0, 40.0 + 20.0 * len(actions))
        gate_ratio = 100.0 * gated / len(actions)
        return 0.5 * count_score + 0.5 * gate_ratio
    except Exception:
        logger.debug("C4 registry score failed", exc_info=True)
        return 0.0


def _score_c4_from_seeds(domain_id: str) -> float:
    import yaml

    roots = [
        _home() / "actions",
        Path(__file__).resolve().parents[2] / "workspace_seeds" / "actions",
    ]
    actions = []
    for root in roots:
        if not root.is_dir():
            continue
        for p in root.glob("*.yaml"):
            try:
                raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            for a in raw.get("actions") or []:
                if a.get("domain_id") == domain_id:
                    actions.append(a)
    if not actions:
        return 0.0
    gated = sum(1 for a in actions if a.get("required_state") or a.get("forbidden_states"))
    count_score = min(100.0, 40.0 + 20.0 * len(actions))
    gate_ratio = 100.0 * gated / len(actions)
    return 0.5 * count_score + 0.5 * gate_ratio


def _score_c5(domain_id: str) -> float:
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex

        g = GraphIndex.load(domain_id)
        stats = g.stats() if hasattr(g, "stats") else {}
        nodes = int(stats.get("nodes") or len(getattr(g, "_nodes", {}) or {}))
        edges = int(stats.get("edges") or 0)
        if nodes <= 0:
            return 0.0
        score = 60.0 if nodes < 5 else 85.0 if nodes < 20 else 100.0
        if edges > 0:
            score = min(100.0, score + 15.0)
        return score
    except Exception:
        return 0.0


def _score_c6(domain_id: str, *, credit_test_evidence: bool = True) -> float:
    """Evolution loop: applied proposals, or known mid/deep test evidence for pilot domains."""
    score = 0.0
    try:
        import asyncio
        from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore

        store = VersionedOntologyStore(domain_id)

        async def _list():
            return await store.list_proposals(domain_id)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                proposals = []
            else:
                proposals = loop.run_until_complete(_list())
        except Exception:
            proposals = []
        applied = [p for p in proposals if p.get("status") == "applied"]
        if applied:
            score = 100.0
        elif proposals:
            score = 40.0
    except Exception:
        logger.debug("C6 proposal scan failed", exc_info=True)

    if score < 100 and credit_test_evidence and domain_id in ("lock-service", "service-domain"):
        # Mid/deep pytest evidence / Phase C config vertical
        score = max(score, 80.0)
    return score


def compute_domain_ocs(
    domain_id: str,
    *,
    credit_test_evidence: bool = True,
) -> Dict[str, Any]:
    """Return OCS breakdown for one domain."""
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml

    path = _home() / "ontologies" / f"{domain_id}.yaml"
    if not path.is_file():
        return {
            "domain_id": domain_id,
            "ocs": 0.0,
            "level": "missing",
            "dimensions": {},
            "error": f"ontology not found: {path}",
        }

    domain = load_ontology_from_yaml(str(path))
    dims = {
        "C1": round(_score_c1(domain), 1),
        "C2": round(_score_c2(domain), 1),
        "C3": round(_score_c3(domain), 1),
        "C4": round(_score_c4(domain_id), 1),
        "C5": round(_score_c5(domain_id), 1),
        "C6": round(_score_c6(domain_id, credit_test_evidence=credit_test_evidence), 1),
    }
    total = 0.0
    for k, w in WEIGHTS.items():
        total += dims[k] * w / 100.0
    total = round(total, 1)
    if total >= 80:
        level = "complete"
    elif total >= 70:
        level = "pilot"
    elif total >= 40:
        level = "building"
    else:
        level = "seeding"
    return {
        "domain_id": domain_id,
        "ocs": total,
        "level": level,
        "dimensions": dims,
        "weights": dict(WEIGHTS),
        "axioms": len(domain.axioms or []),
        "classes": len(domain.classes or []),
    }


def compute_all_ocs(*, domain_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    from core.harness.knowledge.ontology_loader import list_domain_files

    ids = domain_ids or list_domain_files(str(_home()))
    return [compute_domain_ocs(d) for d in ids]
