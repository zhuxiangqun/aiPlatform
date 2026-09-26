"""Org L5 KPI weekly report (it-ops pilot D2) + Phase 3 attribution."""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.apps.org.service.org_runtime import list_runs, ensure_pilot_goal, list_goals


def _median(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    if n % 2:
        return float(s[mid])
    return float((s[mid - 1] + s[mid]) / 2.0)


def weekly_kpi_report(
    domain_id: str = "it-ops",
    goal_id: str = "",
    *,
    week: str = "",
) -> Dict[str, Any]:
    """Compute MTTA / root_cause_rate / exception_ratio + failure TopN + pending HITL."""
    ensure_pilot_goal(domain_id)
    goals = list_goals(domain_id).get("goals") or []
    goal = None
    for g in goals:
        if goal_id and g.get("goal_id") == goal_id:
            goal = g
            break
    if goal is None and goals:
        goal = goals[0]

    gid = str((goal or {}).get("goal_id") or goal_id or "")
    runs = list_runs(gid, limit=50).get("runs") or []
    week_f = (week or "").strip()
    if week_f:
        runs = [r for r in runs if str(r.get("week_label") or "") == week_f]

    mtta_samples: List[float] = []
    triage_n = 0
    root_n = 0
    hitl_n = 0
    step_n = 0
    reason_counter: Counter = Counter()
    pending_hitl: List[Dict[str, Any]] = []

    for r in runs:
        mp = r.get("metrics_partial") or {}
        triage_n += int(mp.get("triage_candidates") or 0)
        root_n += int(mp.get("root_cause_marked") or 0)
        hitl_n += int(mp.get("hitl_steps") or 0)
        step_n += int(mp.get("total_steps") or len(r.get("steps") or []))
        for e in r.get("exceptions") or []:
            if isinstance(e, dict) and e.get("reason"):
                reason_counter[str(e.get("reason"))] += 1
        if r.get("status") == "needs_hitl":
            ticket = None
            for e in r.get("exceptions") or []:
                if isinstance(e, dict) and e.get("hitl_ticket_id"):
                    ticket = e.get("hitl_ticket_id")
                    break
            pending_hitl.append(
                {
                    "run_id": r.get("run_id"),
                    "week_label": r.get("week_label"),
                    "hitl_ticket_id": ticket,
                    "started_at": r.get("started_at"),
                }
            )

    # Graph-level MTTA attempt (state timestamps if present)
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex

        g = GraphIndex.load(domain_id)
        entity_class = str((goal or {}).get("entity_class") or "").strip()
        for node in (getattr(g, "_nodes", {}) or {}).values():
            if entity_class and getattr(node, "class_name", "") != entity_class:
                continue
            meta = getattr(node, "metadata", None) or {}
            opened = meta.get("opened_at") or meta.get("open_ts")
            triaged = meta.get("triaged_at") or meta.get("triage_ts")
            if opened is not None and triaged is not None:
                try:
                    mtta_samples.append(float(triaged) - float(opened))
                except (TypeError, ValueError):  # noqa: cleanup-best-effort
                    pass
    except Exception:  # noqa: cleanup-best-effort
        pass

    root_rate = (root_n / triage_n) if triage_n else None
    exc_ratio = (hitl_n / step_n) if step_n else None
    failure_top = [
        {"reason": reason, "count": count} for reason, count in reason_counter.most_common(5)
    ]

    mem_count = 0
    try:
        from core.apps.org.service.org_memory import list_memory

        mem_count = int(list_memory(limit=200, domain_id=domain_id).get("count") or 0)
    except Exception:  # noqa: cleanup-best-effort
        pass

    return {
        "domain_id": domain_id,
        "goal_id": gid,
        "goal_title": (goal or {}).get("title"),
        "week": week_f or None,
        "run_count": len(runs),
        "kpis": {
            "mtta_seconds": _median(mtta_samples),
            "mtta_note": (
                None
                if mtta_samples
                else "no open→triaged timestamps on graph yet; seed props or Action writeback"
            ),
            "root_cause_rate": root_rate,
            "exception_ratio": exc_ratio,
            "triage_candidates": triage_n,
            "root_cause_marked": root_n,
            "hitl_steps": hitl_n,
            "total_steps": step_n,
        },
        "failure_attribution_top": failure_top,
        "pending_hitl": pending_hitl,
        "memory_entries": mem_count,
        "links": [
            {"label": "业务价值看板", "href": "/diagnostics/business-value"},
            {"label": "FDE⑦", "href": "/diagnostics/fde"},
            {"label": "治理8步", "href": "/knowledge/business?tab=factory"},
        ],
        "authority_note": (
            "pilot D2/D5 KPIs from OrgRuns + org memory; "
            "not Xingye material accuracy claims; no live IO"
        ),
        "status": "ok",
    }


def joint_health_view(domain_id: str = "it-ops") -> Dict[str, Any]:
    """Read-only joint health. Does not write YAML, register actions, or start a fleet."""
    did = (domain_id or "").strip() or "it-ops"
    home = Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))

    explained = 0
    gap = 0
    hit = {"served": 0, "used": 0, "hit_rate": None}
    try:
        from core.harness.knowledge.ontology_case_learning import OntologyCaseStore, context_hit_rate

        loaded = list(OntologyCaseStore(did)._load().values())
        for case in loaded:
            meta = case.metadata or {}
            if case.outcome == "success" and not meta.get("schema_gap"):
                explained += 1
            elif case.outcome == "failure" or meta.get("schema_gap"):
                gap += 1
        hit = context_hit_rate(loaded)
    except Exception:
        explained = 0
        gap = 0
        hit = {"served": 0, "used": 0, "hit_rate": None}

    total = explained + gap
    coverage = (explained / total) if total else None

    repeat = 0
    try:
        from core.apps.org.service.org_skill_draft import list_action_gap_hints

        repeat = len((list_action_gap_hints(domain_id=did).get("items") or []))
    except Exception:
        repeat = 0

    draft_dir = home / "org" / "action_drafts"
    action_drafts = len(list(draft_dir.glob("*.yaml"))) if draft_dir.is_dir() else 0

    skill_dir = home / "org" / "skill_drafts"
    unlisted = 0
    if skill_dir.is_dir():
        for path in skill_dir.glob("*.json"):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(doc, dict) and not doc.get("listed"):
                unlisted += 1

    reh_dir = home / "org" / "rehearsals"
    rehearsals = len(list(reh_dir.glob("*.json"))) if reh_dir.is_dir() else 0
    prev_dir = home / "org" / "event_previews"
    previews = len(list(prev_dir.glob("*.json"))) if prev_dir.is_dir() else 0
    cold_count = 0
    try:
        from core.harness.knowledge.ontology_case_learning import list_cold_cases

        cold_count = int(list_cold_cases(did, limit=1).get("count") or 0)
    except Exception:
        cold_count = 0

    return {
        "ok": True,
        "domain_id": did,
        "explained_count": explained,
        "schema_gap_count": gap,
        "semantic_coverage": coverage,
        "context_served": int(hit.get("served") or 0),
        "context_used": int(hit.get("used") or 0),
        "context_hit_rate": hit.get("hit_rate"),
        "repeat_reject_count": repeat,
        "action_draft_count": action_drafts,
        "action_drafts_registered": False,
        "skill_draft_unlisted": unlisted,
        "rehearsal_count": rehearsals,
        "event_preview_count": previews,
        "cold_archived_count": cold_count,
        "fleet_started": False,
        "wrote_live_yaml": False,
        "m4_claim_allowed": False,
        "authority_note": "联合健康度只读。无案例不报覆盖率。命中率只计已注入且有反馈的案例，无注入不报。冷库不参与注入。不是签收。",
    }
