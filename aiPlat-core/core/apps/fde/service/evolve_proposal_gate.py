"""FDE Phase 4B — evolve_proposal gate (whitelist + HITL, no silent Ontology write).

Uses audit_schema ``evolve_proposal`` + ``check_change_surface``. Does not execute
config mutations — only admits/rejects proposals into a human-review queue file.
"""

from __future__ import annotations

import json
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


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")))


def _queue_dir() -> Path:
    d = _home() / "fde_evolve_proposals"
    d.mkdir(parents=True, exist_ok=True)
    return d


def evaluate_evolve_proposal(
    *,
    keys: List[str],
    proposed_changes: Optional[Dict[str, Any]] = None,
    actor: str = "agent",
    domain_id: str = "",
    touches_abox: bool = False,
    touches_ontology: bool = False,
) -> Dict[str, Any]:
    """Run evolve_proposal gate. Whitelist violations → require HITL / reject.

    Silent ABox/Ontology writes are always blocked (must go through HITL queue).
    """
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
        "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": "No silent ABox/Ontology writes; mutations not applied by this gate",
    }


def _hard_reject(surface: Dict[str, Any]) -> bool:
    """Forbidden keys → reject (not merely HITL)."""
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
    """Evaluate then optionally enqueue for human review. Never mutates Ontology."""
    gate = evaluate_evolve_proposal(
        keys=keys,
        proposed_changes=proposed_changes,
        actor=actor,
        domain_id=domain_id,
        touches_abox=touches_abox,
        touches_ontology=touches_ontology,
    )
    if gate.get("status") == "rejected":
        return {**gate, "proposal_id": None, "queued": False}

    if gate.get("status") == "auto_allow" and not gate.get("require_hitl"):
        # Still queue for audit trail (D6: pass rate not sole KPI) — mark as info
        pass

    proposal_id = f"evo_{uuid.uuid4().hex[:12]}"
    record = {
        "proposal_id": proposal_id,
        "summary": (summary or "")[:500],
        "proposed_changes": proposed_changes or {},
        "gate": gate,
        "review_status": "pending_hitl" if gate.get("require_hitl") else "auto_recorded",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    fp = _queue_dir() / f"{proposal_id}.json"
    fp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
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
