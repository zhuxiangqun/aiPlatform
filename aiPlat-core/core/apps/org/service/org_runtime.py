"""Org L5 runtime — OrgGoal / OrgRun (config-driven; AIPLAT_HOME/org/).

Phase 2: goals + runs + HITL resume. No live customer DB writes.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_GOAL_STATUSES = frozenset({"draft", "active", "paused", "done", "failed"})
_RUN_STATUSES = frozenset(
    {"pending", "running", "needs_hitl", "succeeded", "completed", "completed_partial", "failed", "cancelled"}
)


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def _org_dir() -> Path:
    d = _home() / "org"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _goals_path() -> Path:
    return _org_dir() / "goals.json"


def _runs_path() -> Path:
    return _org_dir() / "runs.json"


def _seed_goal_path(domain_id: str) -> Path:
    return (
        Path(__file__).resolve().parents[4]
        / "workspace_seeds"
        / "org_goals"
        / f"{domain_id}.yaml"
    )


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("org json read failed %s", path, exc_info=True)
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _default_seed(domain_id: str) -> Dict[str, Any]:
    return {
        "goal_id": f"goal-{domain_id}-alert-sla",
        "domain_id": domain_id,
        "title": "开放告警 SLA 内分诊并标注根因",
        "status": "active",
        "kpi_refs": ["mtta", "root_cause_rate", "exception_ratio"],
        "schedule": "manual",
        "owner_role": "ops_owner",
        "allow_fleet": False,
        "query_open": "告警",
        "entity_class": "告警",
        "steps": ["locate", "fetch", "triage_gate"],
        "exception_policy": {
            "triage_requires_hitl": True,
            "max_entities_per_run": 20,
            "fetch_failure": "exception",
        },
    }


def ensure_pilot_goal(domain_id: str = "it-ops") -> Dict[str, Any]:
    """Install seed OrgGoal into AIPLAT_HOME when missing for domain."""
    did = (domain_id or "it-ops").strip() or "it-ops"
    goals = _read_json(_goals_path(), {"goals": []})
    existing = [g for g in goals.get("goals") or [] if g.get("domain_id") == did]
    if existing:
        return {"status": "exists", "goal": existing[0]}

    seed = _default_seed(did)
    sp = _seed_goal_path(did)
    if sp.is_file():
        try:
            import yaml

            raw = yaml.safe_load(sp.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict) and raw.get("goal_id"):
                seed.update({k: v for k, v in raw.items() if v is not None})
        except Exception:
            logger.debug("org goal seed yaml skipped", exc_info=True)

    goals.setdefault("goals", []).append(seed)
    _write_json(_goals_path(), goals)
    return {"status": "installed", "goal": seed}


def list_goals(domain_id: str = "") -> Dict[str, Any]:
    if domain_id:
        ensure_pilot_goal(domain_id)
    else:
        ensure_pilot_goal("it-ops")
    goals = _read_json(_goals_path(), {"goals": []}).get("goals") or []
    if domain_id:
        goals = [g for g in goals if g.get("domain_id") == domain_id]
    return {"goals": goals, "count": len(goals)}


def get_goal(goal_id: str) -> Dict[str, Any]:
    gid = (goal_id or "").strip()
    for g in _read_json(_goals_path(), {"goals": []}).get("goals") or []:
        if g.get("goal_id") == gid:
            return {"status": "ok", "goal": g}
    return {"status": "not_found", "goal_id": gid}


def set_goal_status(goal_id: str, status: str) -> Dict[str, Any]:
    st = (status or "").strip().lower()
    if st not in _GOAL_STATUSES:
        return {"status": "invalid_status", "allowed": sorted(_GOAL_STATUSES)}
    store = _read_json(_goals_path(), {"goals": []})
    found = None
    for g in store.get("goals") or []:
        if g.get("goal_id") == goal_id:
            g["status"] = st
            g["updated_at"] = time.time()
            found = g
            break
    if found is None:
        return {"status": "not_found", "goal_id": goal_id}
    _write_json(_goals_path(), store)
    return {"status": "ok", "goal": found}


def patch_goal(goal_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Patch allowlisted OrgGoal fields (Phase 4 fleet flag etc.)."""
    allow = {"allow_fleet", "title", "schedule", "owner_role", "query_open", "exception_policy"}
    store = _read_json(_goals_path(), {"goals": []})
    found = None
    for g in store.get("goals") or []:
        if g.get("goal_id") == goal_id:
            for k, v in (fields or {}).items():
                if k in allow:
                    g[k] = v
            g["updated_at"] = time.time()
            found = g
            break
    if found is None:
        return {"status": "not_found", "goal_id": goal_id}
    _write_json(_goals_path(), store)
    return {"status": "ok", "goal": found}


def list_runs(goal_id: str = "", limit: int = 20) -> Dict[str, Any]:
    runs = _read_json(_runs_path(), {"runs": []}).get("runs") or []
    if goal_id:
        runs = [r for r in runs if r.get("goal_id") == goal_id]
    runs = sorted(runs, key=lambda r: r.get("started_at") or 0, reverse=True)
    return {"runs": runs[: max(1, min(int(limit), 100))], "count": len(runs)}


def get_run(run_id: str) -> Dict[str, Any]:
    rid = (run_id or "").strip()
    for r in _read_json(_runs_path(), {"runs": []}).get("runs") or []:
        if r.get("run_id") == rid:
            return {"status": "ok", "run": r}
    return {"status": "not_found", "run_id": rid}


def _save_run(run: Dict[str, Any]) -> None:
    store = _read_json(_runs_path(), {"runs": []})
    runs = store.setdefault("runs", [])
    for i, r in enumerate(runs):
        if r.get("run_id") == run.get("run_id"):
            runs[i] = run
            _write_json(_runs_path(), store)
            return
    runs.append(run)
    _write_json(_runs_path(), store)


def _resolve_goal(goal_id: str, domain_id: str) -> Optional[Dict[str, Any]]:
    ensure_pilot_goal(domain_id)
    goals = list_goals(domain_id).get("goals") or []
    gid = (goal_id or "").strip()
    for g in goals:
        if gid and g.get("goal_id") == gid:
            return g
    for g in goals:
        if not gid and g.get("status") == "active":
            return g
    return goals[0] if goals else None


def run_org_goal(
    goal_id: str = "",
    *,
    domain_id: str = "it-ops",
    dry_actions: bool = True,
    week_label: str = "",
    usage_channel: str = "",
    usage_tenant: str = "",
    usage_actor: str = "",
) -> Dict[str, Any]:
    """Execute one OrgRun: locate → fetch → triage_gate (HITL when dry / policy)."""
    from core.apps.fde.service.v_wave_guard import edge_auto_apply_block

    blocked = edge_auto_apply_block()
    if blocked:
        return blocked
    goal = _resolve_goal(goal_id, domain_id)
    if goal is None:
        return {"status": "no_goal", "domain_id": domain_id}
    if goal.get("status") not in ("active", "draft"):
        return {
            "status": "goal_not_runnable",
            "goal_id": goal.get("goal_id"),
            "goal_status": goal.get("status"),
        }

    did = str(goal.get("domain_id") or domain_id)
    policy = goal.get("exception_policy") if isinstance(goal.get("exception_policy"), dict) else {}
    max_n = int(policy.get("max_entities_per_run") or 20)
    require_hitl = bool(policy.get("triage_requires_hitl", True))

    run_id = f"run-{uuid.uuid4().hex[:10]}"
    started = time.time()
    plan_snapshot = {
        "goal_id": goal.get("goal_id"),
        "steps": list(goal.get("steps") or ["locate", "fetch", "triage_gate"]),
        "query_open": goal.get("query_open"),
        "exception_policy": policy,
    }
    steps_out: List[Dict[str, Any]] = []
    exceptions: List[Dict[str, Any]] = []
    triage_count = 0
    root_count = 0
    hitl_steps = 0

    from core.apps.fde.service.governance_deepen import locate_via_ontology
    from core.apps.org.service.org_io import fetch_by_entity

    q = str(goal.get("query_open") or "告警")
    loc = locate_via_ontology(did, q, top_k=min(8, max_n))
    hits = loc.get("hits") or []
    steps_out.append(
        {
            "step": "locate",
            "status": loc.get("status"),
            "hit_count": len(hits),
            "query": q,
        }
    )

    from core.apps.fde.service.k_wave_reason import build_org_run_reasoning

    reasoning = build_org_run_reasoning(did, q, hits if isinstance(hits, list) else [])
    steps_out.append(
        {
            "step": "reasoning",
            "status": reasoning.get("status"),
            "skipped": reasoning.get("skipped") or "",
            "path_count": int(reasoning.get("path_count") or len(reasoning.get("reasoning_paths") or [])),
            "can_execute": False,
            "reasoning_paths": list(reasoning.get("reasoning_paths") or [])[:8],
            "note": reasoning.get("authority_note"),
        }
    )

    fetches: List[Dict[str, Any]] = []
    for h in hits[: min(5, max_n)]:
        eid = str(h.get("entity_id") or "")
        snap = fetch_by_entity(did, eid, purpose="org_run")
        fetches.append(
            {
                "entity_id": eid,
                "status": snap.get("status"),
                "state": (snap.get("graph") or {}).get("state"),
                "sandbox_keys": list((snap.get("sandbox") or {}).keys())[:6],
            }
        )
        if snap.get("status") not in ("ok",):
            exceptions.append(
                {
                    "step": "fetch",
                    "entity_id": eid,
                    "reason": snap.get("status"),
                    "hitl_ticket_id": None,
                }
            )
    steps_out.append({"step": "fetch", "status": "ok", "items": fetches})

    openish = [
        f
        for f in fetches
        if (f.get("state") or "").lower() in ("", "open", "firing", "active")
        or not f.get("state")
    ]
    if dry_actions or (require_hitl and openish):
        hitl_steps += 1
        triage_count += len(openish) or (1 if fetches else 0)
        ticket = f"hitl-{run_id[-6:]}"
        steps_out.append(
            {
                "step": "triage_gate",
                "status": "needs_hitl",
                "candidates": [f.get("entity_id") for f in openish],
                "hitl_ticket_id": ticket,
                "note": "pilot: actions stay HITL/dry until write unlock (D3)",
            }
        )
        exceptions.append(
            {
                "step": "triage_gate",
                "reason": "hitl_required",
                "hitl_ticket_id": ticket,
                "detail": "dry_actions or policy requires human confirm",
            }
        )
    else:
        triage_count += len(openish)
        steps_out.append(
            {
                "step": "triage_gate",
                "status": "auto_skipped_empty" if not openish else "ready",
                "candidates": [f.get("entity_id") for f in openish],
            }
        )

    status = "needs_hitl" if hitl_steps else "succeeded"
    if exceptions and status != "needs_hitl":
        status = "completed_partial"

    run = {
        "run_id": run_id,
        "trace_id": run_id,
        "trace_origin": "run",
        "goal_id": goal.get("goal_id"),
        "domain_id": did,
        "week_label": week_label or "",
        "started_at": started,
        "finished_at": time.time(),
        "status": status,
        "plan_snapshot": plan_snapshot,
        "steps": steps_out,
        "exceptions": exceptions,
        "reasoning": reasoning,
        "metrics_partial": {
            "triage_candidates": triage_count,
            "root_cause_marked": root_count,
            "hitl_steps": hitl_steps,
            "total_steps": len(steps_out),
            "reasoning_paths": int(reasoning.get("path_count") or 0),
        },
        "authority_note": "org L5 Phase 2 run; K3 paths are evidence only; sandbox fetch; no production write",
    }
    _save_run(run)
    try:
        from core.apps.org.service.org_memory import record_run_memory

        run["memory"] = record_run_memory(run)
    except Exception:
        logger.debug("org memory record skipped", exc_info=True)
    try:
        from core.apps.org.service.org_usage import schedule_run_usage

        run["usage"] = schedule_run_usage(
            run,
            channel=usage_channel,
            tenant_id=usage_tenant,
            actor_id=usage_actor,
        )
    except Exception:
        logger.debug("org usage schedule skipped", exc_info=True)
        run["usage"] = {"status": "skipped", "billing": None}
    try:
        from core.apps.fde.service.k_wave_case import record_case_from_org_run

        run["case"] = record_case_from_org_run(run)
    except Exception:
        logger.debug("org K4 case record skipped", exc_info=True)
        run["case"] = {"status": "skipped"}
    return run


def resume_run(
    run_id: str,
    *,
    approve: bool = True,
    resolution: str = "",
) -> Dict[str, Any]:
    """Resume needs_hitl run after human decision (W4)."""
    got = get_run(run_id)
    if got.get("status") != "ok":
        return got
    run = dict(got["run"])
    if run.get("status") != "needs_hitl":
        return {
            "status": "not_waiting",
            "run_id": run_id,
            "run_status": run.get("status"),
        }

    if not approve:
        run["status"] = "cancelled"
        run["finished_at"] = time.time()
        run["exceptions"] = list(run.get("exceptions") or []) + [
            {
                "step": "triage_gate",
                "reason": "hitl_rejected",
                "detail": resolution or "operator rejected",
            }
        ]
        _save_run(run)
        try:
            from core.apps.org.service.org_memory import record_run_memory

            run["memory"] = record_run_memory(run)
        except Exception:
            logger.debug("org memory record skipped", exc_info=True)
        return {"status": "ok", "run": run}

    # Approve: mark triage_gate resolved; still no live Action write (D3)
    new_steps = []
    for step in run.get("steps") or []:
        if step.get("step") == "triage_gate" and step.get("status") == "needs_hitl":
            new_steps.append(
                {
                    **step,
                    "status": "approved_dry",
                    "resolution": resolution or "approved",
                    "note": "HITL approved; Action execute still dry (D3)",
                }
            )
        else:
            new_steps.append(step)
    run["steps"] = new_steps
    run["exceptions"] = [
        e
        for e in (run.get("exceptions") or [])
        if e.get("reason") != "hitl_required"
    ]
    mp = dict(run.get("metrics_partial") or {})
    # keep hitl_steps historical count; mark resolved
    mp["hitl_resolved"] = 1
    run["metrics_partial"] = mp
    run["status"] = "succeeded"
    run["finished_at"] = time.time()
    run["authority_note"] = "HITL resumed; sandbox only; no production write"
    _save_run(run)
    try:
        from core.apps.org.service.org_memory import record_run_memory

        run["memory"] = record_run_memory(run)
    except Exception:
        logger.debug("org memory record skipped", exc_info=True)
    return {"status": "ok", "run": run}
