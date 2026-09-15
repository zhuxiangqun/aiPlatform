"""FDE Phase 4B — evolve_proposal gate + controlled apply/rollback + observation window.

Whitelist config keys only. Never silently writes ABox/Ontology.
D6 metrics: reject_rate, rollback_rate, mean_survival_hours (pass_rate is reference only).
Design: docs/contracts/FDE_AI_FDE_CONTROLLED_APPLY_LOOP.md
"""

from __future__ import annotations

import calendar
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.harness.infrastructure.action_audit_validate import (
    check_change_surface,
    load_audit_schema,
)


GATE_ID = "evolve_proposal"
logger = logging.getLogger(__name__)

# Statuses that hold an active config patch (can rollback)
_ACTIVE_PATCH = frozenset({"observing", "applied", "stable"})


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")))


def _queue_dir() -> Path:
    d = _home() / "fde_evolve_proposals"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _config_path() -> Path:
    return _home() / "fde_evolve_applied_config.json"


def _metrics_path() -> Path:
    return _home() / "fde_evolve_metrics.json"


def _observations_path() -> Path:
    return _home() / "fde_evolve_observations.json"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _observation_hours() -> float:
    try:
        return max(1e-6, float(os.getenv("AIPLAT_EVOLVE_OBSERVATION_HOURS", "24")))
    except Exception:
        return 24.0


def _quality_drop_threshold() -> float:
    """Auto-rollback when quality_score drops more than this vs baseline (points)."""
    try:
        return float(os.getenv("AIPLAT_EVOLVE_QUALITY_DROP_THRESHOLD", "10"))
    except Exception:
        return 10.0


def _observation_until_iso(from_ts: Optional[float] = None) -> str:
    base = from_ts if from_ts is not None else time.time()
    until = base + _observation_hours() * 3600.0
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(until))


def evaluate_evolve_proposal(
    *,
    keys: List[str],
    proposed_changes: Optional[Dict[str, Any]] = None,
    actor: str = "agent",
    domain_id: str = "",
    touches_abox: bool = False,
    touches_ontology: bool = False,
) -> Dict[str, Any]:
    """Run evolve_proposal gate. Whitelist violations → require HITL / reject."""
    schema = load_audit_schema()
    gates = ((schema.get("eval_gate") or {}).get("gates") or {})
    gate_def = gates.get(GATE_ID) or {}
    surface = check_change_surface(list(keys or []), schema=schema)

    reasons: List[str] = []
    passed = True
    require_hitl = bool(surface.get("require_hitl"))

    if not surface.get("ok"):
        passed = False
        reasons.append("change_surface_violation")
        require_hitl = True

    if touches_abox or touches_ontology:
        passed = False
        require_hitl = True
        reasons.append("abox_or_ontology_write_requires_hitl")

    criteria = gate_def.get("criteria") or {}
    if criteria.get("manual_approval_required") and (not surface.get("ok") or touches_abox or touches_ontology):
        require_hitl = True

    if criteria.get("change_surface_whitelist") and not surface.get("ok"):
        passed = False

    status = "admitted_to_hitl" if (require_hitl and not _hard_reject(surface)) else (
        "rejected" if not passed else "auto_allow"
    )
    if _hard_reject(surface):
        status = "rejected"
        passed = False

    return {
        "gate_id": GATE_ID,
        "passed": passed and status != "rejected",
        "status": status,
        "require_hitl": require_hitl,
        "reasons": reasons,
        "change_surface": surface,
        "actor": actor,
        "domain_id": domain_id,
        "keys": list(keys or []),
        "proposed_change_count": len(proposed_changes or {}),
        "evaluated_at": _now(),
        "note": "No silent ABox/Ontology writes; apply only after HITL via apply_evolve_proposal",
    }


def _hard_reject(surface: Dict[str, Any]) -> bool:
    for v in surface.get("violations") or []:
        if isinstance(v, dict) and v.get("reason") == "forbidden":
            return True
    action = str(surface.get("action") or "")
    return action == "hitl_and_reject" and any(
        isinstance(v, dict) and v.get("reason") == "forbidden"
        for v in (surface.get("violations") or [])
    )


def enqueue_evolve_proposal(
    *,
    keys: List[str],
    proposed_changes: Optional[Dict[str, Any]] = None,
    actor: str = "agent",
    domain_id: str = "",
    touches_abox: bool = False,
    touches_ontology: bool = False,
    summary: str = "",
) -> Dict[str, Any]:
    gate = evaluate_evolve_proposal(
        keys=keys,
        proposed_changes=proposed_changes,
        actor=actor,
        domain_id=domain_id,
        touches_abox=touches_abox,
        touches_ontology=touches_ontology,
    )
    if gate.get("status") == "rejected":
        _metrics_inc("rejected_at_gate")
        return {**gate, "proposal_id": None, "queued": False}

    proposal_id = f"evo_{uuid.uuid4().hex[:12]}"
    record = {
        "proposal_id": proposal_id,
        "summary": (summary or "")[:500],
        "proposed_changes": proposed_changes or {},
        "keys": list(keys or []),
        "gate": gate,
        "review_status": "pending_hitl" if gate.get("require_hitl") else "auto_recorded",
        "touches_abox": bool(touches_abox),
        "touches_ontology": bool(touches_ontology),
        "domain_id": domain_id,
        "actor": actor,
        "created_at": _now(),
        "applied_snapshot": None,
        "applied_at": None,
        "rolled_back_at": None,
    }
    _save(record)
    _metrics_inc("queued")
    return {**gate, "proposal_id": proposal_id, "queued": True, "review_status": record["review_status"]}


def list_evolve_proposals(limit: int = 20) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for fp in sorted(_queue_dir().glob("evo_*.json"), reverse=True):
        try:
            rows.append(json.loads(fp.read_text(encoding="utf-8")))
        except Exception:
            continue
        if len(rows) >= limit:
            break
    return rows


def get_evolve_proposal(proposal_id: str) -> Optional[Dict[str, Any]]:
    fp = _queue_dir() / f"{proposal_id}.json"
    if not fp.is_file():
        return None
    return json.loads(fp.read_text(encoding="utf-8"))


def _save(record: Dict[str, Any]) -> None:
    fp = _queue_dir() / f"{record['proposal_id']}.json"
    tmp = fp.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(fp)


def approve_evolve_proposal(proposal_id: str, actor: str = "approver") -> Dict[str, Any]:
    rec = get_evolve_proposal(proposal_id)
    if not rec:
        raise FileNotFoundError(proposal_id)
    if rec.get("review_status") not in {"pending_hitl", "auto_recorded"}:
        raise ValueError(f"cannot approve status={rec.get('review_status')}")
    if rec.get("touches_abox") or rec.get("touches_ontology"):
        # Still allow approve into queue for human apply decision, but apply will refuse ABox
        pass
    rec["review_status"] = "approved"
    rec["approved_by"] = actor
    rec["approved_at"] = _now()
    _save(rec)
    _metrics_inc("approved")
    return rec


def reject_evolve_proposal(proposal_id: str, actor: str = "approver", reason: str = "") -> Dict[str, Any]:
    rec = get_evolve_proposal(proposal_id)
    if not rec:
        raise FileNotFoundError(proposal_id)
    if rec.get("review_status") in _ACTIVE_PATCH or rec.get("review_status") == "rolled_back":
        raise ValueError(f"cannot reject status={rec.get('review_status')}")
    rec["review_status"] = "rejected"
    rec["rejected_by"] = actor
    rec["rejected_at"] = _now()
    rec["reject_reason"] = (reason or "")[:500]
    _save(rec)
    _metrics_inc("rejected_hitl")
    return rec


def apply_evolve_proposal(proposal_id: str, actor: str = "approver") -> Dict[str, Any]:
    """Apply whitelist config keys, then enter observation window (status=observing)."""
    rec = get_evolve_proposal(proposal_id)
    if not rec:
        raise FileNotFoundError(proposal_id)
    if rec.get("review_status") not in {"approved", "auto_recorded"}:
        raise ValueError("proposal must be approved (or auto_recorded) before apply")
    if rec.get("touches_abox") or rec.get("touches_ontology"):
        raise ValueError("abox/ontology proposals cannot be applied by this path")

    changes = rec.get("proposed_changes") or {}
    keys = list(rec.get("keys") or changes.keys())
    surface = check_change_surface(keys)
    if not surface.get("ok") or _hard_reject(surface):
        raise ValueError(f"change_surface blocked: {surface.get('violations')}")

    cfg = _load_config()
    snapshot = {k: cfg.get(k) for k in keys}
    for k, v in changes.items():
        if k in keys:
            cfg[k] = v
    _write_config(cfg)
    after = {k: cfg.get(k) for k in keys}

    applied_at = _now()
    rec["applied_snapshot"] = snapshot
    rec["after_snapshot"] = after
    rec["review_status"] = "observing"
    rec["applied_by"] = actor
    rec["applied_at"] = applied_at
    rec["observation_until"] = _observation_until_iso()
    rec["observations"] = list(rec.get("observations") or [])
    _save(rec)
    _metrics_inc("applied")
    _metrics_inc("observing")
    return rec


def rollback_evolve_proposal(
    proposal_id: str,
    actor: str = "approver",
    *,
    reason: str = "manual",
) -> Dict[str, Any]:
    """Rollback active patch (observing / applied / stable). Records survival for D6."""
    rec = get_evolve_proposal(proposal_id)
    if not rec:
        raise FileNotFoundError(proposal_id)
    if rec.get("review_status") not in _ACTIVE_PATCH:
        raise ValueError("only observing/applied/stable proposals can be rolled back")
    snapshot = rec.get("applied_snapshot") or {}
    cfg = _load_config()
    for k, prev in snapshot.items():
        if prev is None:
            cfg.pop(k, None)
        else:
            cfg[k] = prev
    _write_config(cfg)
    rec["review_status"] = "rolled_back"
    rec["rolled_back_by"] = actor
    rec["rolled_back_at"] = _now()
    rec["rollback_reason"] = (reason or "manual")[:200]
    _save(rec)
    _metrics_inc("rolled_back")
    try:
        applied = rec.get("applied_at") or ""
        if applied:
            _metrics_event("survival_seconds", max(0, int(time.time() - _parse_ts(applied))))
    except Exception:
        logger.debug("survival metric skipped", exc_info=True)
    return rec


def list_evolve_applied(limit: int = 20) -> List[Dict[str, Any]]:
    """Proposals that entered apply (observing / stable / applied / rolled_back)."""
    want = _ACTIVE_PATCH | {"rolled_back"}
    rows = [p for p in list_evolve_proposals(max(limit * 3, 50)) if p.get("review_status") in want]
    return rows[:limit]


def record_evolve_observation(
    proposal_id: str,
    *,
    metric_name: str,
    metric_value: float,
    baseline_value: Optional[float] = None,
    actor: str = "system",
) -> Dict[str, Any]:
    """Append observation sample; auto-rollback on quality_score breach."""
    rec = get_evolve_proposal(proposal_id)
    if not rec:
        raise FileNotFoundError(proposal_id)
    if rec.get("review_status") not in _ACTIVE_PATCH:
        raise ValueError("can only observe active patches")

    name = (metric_name or "")[:80]
    verdict = "ok"
    baseline = baseline_value
    if name == "quality_score" and baseline is not None:
        drop = float(baseline) - float(metric_value)
        if drop > _quality_drop_threshold():
            verdict = "breach"

    obs = {
        "observation_id": f"obs_{uuid.uuid4().hex[:10]}",
        "proposal_id": proposal_id,
        "metric_name": name,
        "metric_value": float(metric_value),
        "baseline_value": float(baseline) if baseline is not None else None,
        "window_start": rec.get("applied_at"),
        "window_end": rec.get("observation_until"),
        "verdict": verdict,
        "recorded_at": _now(),
        "actor": actor,
    }
    arr = list(rec.get("observations") or [])
    arr.append(obs)
    rec["observations"] = arr[-50:]
    _save(rec)
    _append_observation_index(obs)

    if verdict == "breach":
        return rollback_evolve_proposal(proposal_id, actor=actor, reason="quality_score_breach")
    return {"proposal": rec, "observation": obs}


def tick_evolve_observations(actor: str = "system") -> Dict[str, Any]:
    """Promote observing → stable when observation_until elapsed; record survival."""
    now = time.time()
    promoted: List[str] = []
    still: List[str] = []
    for rec in list_evolve_proposals(100):
        if rec.get("review_status") != "observing":
            continue
        until = rec.get("observation_until") or ""
        try:
            until_ts = _parse_ts(until) if until else 0.0
        except Exception:
            until_ts = 0.0
        if until_ts and now >= until_ts:
            rec["review_status"] = "stable"
            rec["stable_at"] = _now()
            _save(rec)
            _metrics_inc("stable")
            try:
                applied = rec.get("applied_at") or ""
                if applied:
                    _metrics_event(
                        "survival_seconds",
                        max(0, int(until_ts - _parse_ts(applied))),
                    )
            except Exception:
                logger.debug("stable survival metric skipped", exc_info=True)
            promoted.append(rec["proposal_id"])
        else:
            still.append(rec.get("proposal_id") or "")
    return {
        "promoted_stable": promoted,
        "still_observing": still,
        "observation_hours": _observation_hours(),
    }


def get_evolve_metrics() -> Dict[str, Any]:
    """D6 reverse metrics — pass_rate is reference only, never sole KPI."""
    raw = _load_metrics()
    queued = int(raw.get("queued") or 0)
    approved = int(raw.get("approved") or 0)
    rejected_hitl = int(raw.get("rejected_hitl") or 0)
    rejected_gate = int(raw.get("rejected_at_gate") or 0)
    applied = int(raw.get("applied") or 0)
    rolled = int(raw.get("rolled_back") or 0)
    stable = int(raw.get("stable") or 0)
    decided = approved + rejected_hitl
    reject_rate = (rejected_hitl / decided) if decided else 0.0
    rollback_rate = (rolled / applied) if applied else 0.0
    survivals = raw.get("survival_seconds") or []
    if not isinstance(survivals, list):
        survivals = []
    mean_survival_h = (sum(survivals) / len(survivals) / 3600.0) if survivals else None
    pass_rate_ref = (approved / decided) if decided else None
    props = list_evolve_proposals(100)
    return {
        "queued": queued,
        "approved": approved,
        "rejected_hitl": rejected_hitl,
        "rejected_at_gate": rejected_gate,
        "applied": applied,
        "rolled_back": rolled,
        "stable": stable,
        "observing": len([p for p in props if p.get("review_status") == "observing"]),
        "reject_rate": round(reject_rate, 4),
        "rollback_rate": round(rollback_rate, 4),
        "mean_survival_hours": round(mean_survival_h, 4) if mean_survival_h is not None else None,
        "pass_rate_reference_only": round(pass_rate_ref, 4) if pass_rate_ref is not None else None,
        "note": "D6: pass_rate is reference only; use reject_rate + rollback_rate + survival",
        "pending_hitl": len([p for p in props if p.get("review_status") == "pending_hitl"]),
    }



def get_evolve_applied_config() -> Dict[str, Any]:
    return _load_config()


def _load_config() -> Dict[str, Any]:
    fp = _config_path()
    if not fp.is_file():
        return {}
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_config(cfg: Dict[str, Any]) -> None:
    fp = _config_path()
    tmp = fp.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(fp)


def _load_metrics() -> Dict[str, Any]:
    fp = _metrics_path()
    if not fp.is_file():
        return {}
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _metrics_inc(key: str) -> None:
    m = _load_metrics()
    m[key] = int(m.get(key) or 0) + 1
    _metrics_path().write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


def _metrics_event(key: str, value: Any) -> None:
    m = _load_metrics()
    arr = m.get(key)
    if not isinstance(arr, list):
        arr = []
    arr.append(value)
    m[key] = arr[-200:]
    _metrics_path().write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_observation_index(obs: Dict[str, Any]) -> None:
    fp = _observations_path()
    rows: List[Dict[str, Any]] = []
    if fp.is_file():
        try:
            raw = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                rows = raw
        except Exception:
            rows = []
    rows.append(obs)
    fp.write_text(json.dumps(rows[-500:], ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_ts(iso: str) -> float:
    # %Y-%m-%dT%H:%M:%SZ as UTC
    try:
        return calendar.timegm(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return time.time()
