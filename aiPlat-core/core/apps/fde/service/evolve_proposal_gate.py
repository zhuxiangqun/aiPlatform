"""FDE Phase 4B — evolve_proposal gate + controlled apply/rollback (AI FDE half-step).

Whitelist config keys only. Never silently writes ABox/Ontology.
D6 metrics: reject_rate, rollback_rate, mean_survival_hours (pass_rate is reference only).
"""

from __future__ import annotations

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


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


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
    if rec.get("review_status") in {"applied", "rolled_back"}:
        raise ValueError(f"cannot reject status={rec.get('review_status')}")
    rec["review_status"] = "rejected"
    rec["rejected_by"] = actor
    rec["rejected_at"] = _now()
    rec["reject_reason"] = (reason or "")[:500]
    _save(rec)
    _metrics_inc("rejected_hitl")
    return rec


def apply_evolve_proposal(proposal_id: str, actor: str = "approver") -> Dict[str, Any]:
    """Apply whitelist config keys to AIPLAT_HOME evolve config store. No Ontology writes."""
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

    rec["applied_snapshot"] = snapshot
    rec["review_status"] = "applied"
    rec["applied_by"] = actor
    rec["applied_at"] = _now()
    _save(rec)
    _metrics_inc("applied")
    return rec


def rollback_evolve_proposal(proposal_id: str, actor: str = "approver") -> Dict[str, Any]:
    rec = get_evolve_proposal(proposal_id)
    if not rec:
        raise FileNotFoundError(proposal_id)
    if rec.get("review_status") != "applied":
        raise ValueError("only applied proposals can be rolled back")
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
    _save(rec)
    _metrics_inc("rolled_back")
    # survival hours for D6
    try:
        applied = rec.get("applied_at") or ""
        if applied:
            # coarse: store seconds between apply and rollback in metrics events
            _metrics_event("survival_seconds", max(0, int(time.time() - _parse_ts(applied))))
    except Exception:
        logger.debug("survival metric skipped", exc_info=True)
    return rec


def get_evolve_metrics() -> Dict[str, Any]:
    """D6 reverse metrics — pass_rate is reference only, never sole KPI."""
    raw = _load_metrics()
    queued = int(raw.get("queued") or 0)
    approved = int(raw.get("approved") or 0)
    rejected_hitl = int(raw.get("rejected_hitl") or 0)
    rejected_gate = int(raw.get("rejected_at_gate") or 0)
    applied = int(raw.get("applied") or 0)
    rolled = int(raw.get("rolled_back") or 0)
    decided = approved + rejected_hitl
    reject_rate = (rejected_hitl / decided) if decided else 0.0
    rollback_rate = (rolled / applied) if applied else 0.0
    survivals = raw.get("survival_seconds") or []
    if not isinstance(survivals, list):
        survivals = []
    mean_survival_h = (sum(survivals) / len(survivals) / 3600.0) if survivals else None
    pass_rate_ref = (approved / decided) if decided else None
    return {
        "queued": queued,
        "approved": approved,
        "rejected_hitl": rejected_hitl,
        "rejected_at_gate": rejected_gate,
        "applied": applied,
        "rolled_back": rolled,
        "reject_rate": round(reject_rate, 4),
        "rollback_rate": round(rollback_rate, 4),
        "mean_survival_hours": round(mean_survival_h, 4) if mean_survival_h is not None else None,
        "pass_rate_reference_only": round(pass_rate_ref, 4) if pass_rate_ref is not None else None,
        "note": "D6: pass_rate is reference only; use reject_rate + rollback_rate + survival",
        "pending_hitl": len([p for p in list_evolve_proposals(100) if p.get("review_status") == "pending_hitl"]),
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


def _parse_ts(iso: str) -> float:
    # %Y-%m-%dT%H:%M:%SZ
    try:
        return time.mktime(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return time.time()
