"""Phase K2 — arbitration tickets before cross-domain edge writes.

Candidates become tickets. CrossDomainResolver.resolve runs only after
an approved merge ticket is applied. Exact-key hits still need a human click.
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

_STATUSES = frozenset(
    {"pending", "approved", "rejected", "deferred", "conflict", "superseded"}
)
_DECISIONS = frozenset({"merge", "add", "reject", "defer", "conflict"})
_DEFER_SEC = 14 * 86400
_CONFLICT_HOLD_SEC = 7 * 86400


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def tickets_path() -> Path:
    return _home() / "k_wave" / "arbitration.jsonl"


def _read_all() -> List[Dict[str, Any]]:
    path = tickets_path()
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _rewrite(rows: List[Dict[str, Any]]) -> None:
    path = tickets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _append(row: Dict[str, Any]) -> None:
    path = tickets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _apply_timeouts(row: Dict[str, Any], *, now: Optional[float] = None) -> Dict[str, Any]:
    out = dict(row)
    ts = float(out.get("updated_at") or out.get("created_at") or 0)
    clock = now if now is not None else time.time()
    status = str(out.get("status") or "")
    if status == "deferred" and ts and (clock - ts) >= _DEFER_SEC:
        out["status"] = "rejected"
        out["timeout_reason"] = "deferred_expired"
        out["updated_at"] = clock
    elif status == "conflict" and ts and (clock - ts) >= _CONFLICT_HOLD_SEC:
        out["timeout_note"] = "conflict_held"
    return out


def get_ticket(ticket_id: str) -> Optional[Dict[str, Any]]:
    tid = (ticket_id or "").strip()
    if not tid:
        return None
    for row in _read_all():
        if row.get("ticket_id") == tid:
            return _apply_timeouts(row)
    return None


def list_tickets(
    *,
    status: str = "",
    domain_id: str = "",
    tenant_id: str = "",
) -> Dict[str, Any]:
    want = (status or "").strip()
    did = (domain_id or "").strip()
    tid = (tenant_id or "").strip()
    items: List[Dict[str, Any]] = []
    dirty = False
    rows = _read_all()
    refreshed: List[Dict[str, Any]] = []
    for row in rows:
        fresh = _apply_timeouts(row)
        if fresh.get("status") != row.get("status") or fresh.get("timeout_reason"):
            dirty = True
        refreshed.append(fresh)
        if want and fresh.get("status") != want:
            continue
        if did and did not in (
            str(fresh.get("left_domain") or ""),
            str(fresh.get("right_domain") or ""),
            str(fresh.get("domain_id") or ""),
        ):
            continue
        if tid:
            lt = str(fresh.get("left_tenant") or "")
            rt = str(fresh.get("right_tenant") or "")
            if tid not in (lt, rt) and lt and rt:
                continue
            if tid not in (lt, rt, "") and (lt or rt):
                # require match when tenant filter set
                if tid != lt and tid != rt:
                    continue
        items.append(fresh)
    if dirty:
        _rewrite(refreshed)
    return {"status": "ok", "count": len(items), "items": items}


def propose_ticket(
    *,
    view_name: str = "",
    left_id: str = "",
    right_id: str = "",
    left_domain: str = "",
    right_domain: str = "",
    left_tenant: str = "",
    right_tenant: str = "",
    confidence: float = 0.0,
    strategy: str = "",
    suggested: str = "merge",
    trace_id: str = "",
    signal_id: str = "",
    extract_actor: str = "",
    evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Open a pending (or auto-rejected) arbitration ticket. Never writes an edge."""
    lid = (left_id or "").strip()
    rid = (right_id or "").strip()
    ld = (left_domain or "").strip()
    rd = (right_domain or "").strip()
    if not all([lid, rid, ld, rd]):
        return {"ok": False, "reason": "need_left_right_ids_and_domains"}

    lt = (left_tenant or "").strip()
    rt = (right_tenant or "").strip()
    now = time.time()
    ticket_id = f"arb-{uuid.uuid4().hex[:12]}"
    sug = (suggested or "merge").strip().lower()
    if sug not in _DECISIONS:
        sug = "merge"

    status = "pending"
    reason = ""
    if lt and rt and lt != rt:
        status = "rejected"
        reason = "cross_tenant"
        sug = "reject"

    # Idempotent open ticket for same pair while pending/approved unused
    for row in _read_all():
        fresh = _apply_timeouts(row)
        if (
            fresh.get("left_id") == lid
            and fresh.get("right_id") == rid
            and fresh.get("left_domain") == ld
            and fresh.get("right_domain") == rd
            and fresh.get("status") in ("pending", "approved")
            and not fresh.get("applied")
        ):
            return {**fresh, "ok": True, "idempotent": True}

    event = {
        "ticket_id": ticket_id,
        "status": status,
        "suggested": sug,
        "decision": sug if status == "rejected" else "",
        "view_name": (view_name or "").strip() or "default",
        "left_id": lid,
        "right_id": rid,
        "left_domain": ld,
        "right_domain": rd,
        "left_tenant": lt,
        "right_tenant": rt,
        "confidence": float(confidence or 0),
        "strategy": (strategy or "").strip(),
        "trace_id": (trace_id or "").strip() or uuid.uuid4().hex,
        "trace_origin": "arbitration_propose" if not (trace_id or "").strip() else "inherited",
        "signal_id": (signal_id or "").strip(),
        "extract_actor": (extract_actor or "").strip(),
        "arbit_actor": "",
        "batch_id": "",
        "evidence": evidence if isinstance(evidence, dict) else {},
        "reason": reason,
        "applied": False,
        "edge_written": False,
        "created_at": now,
        "updated_at": now,
        "authority_note": "K2 ticket only; not an edge until approved+applied",
    }
    _append(event)
    return {"ok": True, "idempotent": False, **event}


def decide_ticket(
    ticket_id: str,
    *,
    decision: str,
    actor: str = "",
    note: str = "",
) -> Dict[str, Any]:
    """Human decision. Does not write edges. Does not call apply_proposal."""
    tid = (ticket_id or "").strip()
    dec = (decision or "").strip().lower()
    if dec not in _DECISIONS:
        return {"ok": False, "reason": "bad_decision", "allowed": sorted(_DECISIONS)}
    rows = _read_all()
    found = None
    idx = -1
    for i, row in enumerate(rows):
        if row.get("ticket_id") == tid:
            found = _apply_timeouts(row)
            idx = i
            break
    if found is None:
        return {"ok": False, "reason": "not_found", "ticket_id": tid}
    if found.get("status") in ("superseded",):
        return {"ok": False, "reason": "superseded", "ticket": found}
    if found.get("applied"):
        return {"ok": False, "reason": "already_applied", "ticket": found}

    now = time.time()
    if dec == "reject":
        status = "rejected"
    elif dec == "defer":
        status = "deferred"
    elif dec == "conflict":
        status = "conflict"
    elif dec in ("merge", "add"):
        status = "approved"
    else:
        status = "pending"

    # supersede other open tickets for same pair
    for j, row in enumerate(rows):
        if j == idx:
            continue
        if (
            row.get("left_id") == found.get("left_id")
            and row.get("right_id") == found.get("right_id")
            and row.get("left_domain") == found.get("left_domain")
            and row.get("right_domain") == found.get("right_domain")
            and row.get("status") in ("pending", "deferred", "conflict", "approved")
            and not row.get("applied")
        ):
            row["status"] = "superseded"
            row["updated_at"] = now
            row["superseded_by"] = tid

    found.update(
        {
            "status": status,
            "decision": dec,
            "arbit_actor": (actor or "").strip(),
            "decision_note": (note or "").strip(),
            "updated_at": now,
        }
    )
    rows[idx] = found
    _rewrite(rows)
    return {"ok": True, "ticket": found}


def _copy_json(value: Any) -> Any:
    if value is None:
        return None
    return json.loads(json.dumps(value, ensure_ascii=False))


def _read_cross_domain(domain_id: str, entity_id: str) -> Any:
    from core.harness.ontology_engine.graph_index import GraphIndex

    node = GraphIndex.load(domain_id).get_node(entity_id)
    if node is None or not isinstance(getattr(node, "metadata", None), dict):
        return None
    raw = node.metadata.get("_cross_domain")
    if raw is None:
        return None
    return _copy_json(raw)


def _capture_edge_before(ticket: Dict[str, Any]) -> Dict[str, Any]:
    """Read both sides before resolve. Missing entity is null, not a failure."""
    try:
        left = _read_cross_domain(
            str(ticket.get("left_domain") or ""),
            str(ticket.get("left_id") or ""),
        )
        right = _read_cross_domain(
            str(ticket.get("right_domain") or ""),
            str(ticket.get("right_id") or ""),
        )
    except Exception:
        logger.warning("edge_before capture failed", exc_info=True)
        return {"ok": False, "reason": "edge_before_capture_failed"}
    return {"ok": True, "edge_before": {"left": left, "right": right}}


def apply_ticket(ticket_id: str, *, actor: str = "") -> Dict[str, Any]:
    """Apply an approved merge ticket. Snapshot _cross_domain, then resolve once."""
    tid = (ticket_id or "").strip()
    rows = _read_all()
    found = None
    idx = -1
    for i, row in enumerate(rows):
        if row.get("ticket_id") == tid:
            found = _apply_timeouts(row)
            idx = i
            break
    if found is None:
        return {"ok": False, "reason": "not_found", "ticket_id": tid}
    if found.get("edge_rolled_back"):
        return {
            "ok": False,
            "reason": "already_rolled_back",
            "ticket_id": tid,
            "edge_written": False,
        }
    if found.get("applied") and found.get("edge_written"):
        return {"ok": True, "idempotent": True, "ticket": found, "edge_written": True}
    if found.get("status") != "approved":
        return {
            "ok": False,
            "reason": "not_approved",
            "status": found.get("status"),
            "ticket_id": tid,
        }
    if found.get("decision") != "merge":
        # add: graph node write deferred; reject/defer never apply
        return {
            "ok": False,
            "reason": "decision_not_merge",
            "decision": found.get("decision"),
            "authority_note": "K2 apply only writes edges for decision=merge",
            "ticket": found,
        }

    snap = _capture_edge_before(found)
    if not snap.get("ok"):
        return {
            "ok": False,
            "reason": snap.get("reason") or "edge_before_capture_failed",
            "ticket_id": tid,
            "edge_written": False,
        }
    found["edge_before"] = snap["edge_before"]
    rows[idx] = found
    _rewrite(rows)

    from core.harness.knowledge_pipeline.resolver import CrossDomainResolver

    ok = CrossDomainResolver.resolve(
        str(found.get("view_name") or "default"),
        str(found.get("left_id") or ""),
        str(found.get("right_id") or ""),
        str(found.get("left_domain") or ""),
        str(found.get("right_domain") or ""),
        float(found.get("confidence") or 0),
    )
    now = time.time()
    found.update(
        {
            "applied": True,
            "edge_written": bool(ok),
            "apply_actor": (actor or found.get("arbit_actor") or "").strip(),
            "applied_at": now,
            "updated_at": now,
            "apply_ok": bool(ok),
        }
    )
    rows[idx] = found
    _rewrite(rows)
    if not ok:
        return {"ok": False, "reason": "resolve_failed", "ticket": found, "edge_written": False}
    return {"ok": True, "idempotent": False, "ticket": found, "edge_written": True}


def _points_at(current: Any, other_id: str, other_domain: str) -> bool:
    if not isinstance(current, dict):
        return False
    if str(current.get("target_id") or "") != other_id:
        return False
    target_domain = str(current.get("target_domain") or "")
    return not target_domain or target_domain == other_domain


def _restore_cross_domain(domain_id: str, entity_id: str, value: Any) -> bool:
    from core.harness.ontology_engine.graph_index import GraphIndex

    graph = GraphIndex.load(domain_id)
    if graph.get_node(entity_id) is None:
        return value is None
    stored = None if value is None else _copy_json(value)
    return graph.set_entity_property(entity_id, "_cross_domain", stored)


def rollback_ticket_edge(ticket_id: str, *, role: str) -> Dict[str, Any]:
    """E2: restore one merge ticket's _cross_domain from edge_before. Not live YAML."""
    from core.harness.infrastructure.gates.policy_gate import PolicyDecision, PolicyGate
    from core.harness.knowledge.knowledge_ontology import TIER_EDGE

    decision = PolicyGate().decide_ontology_approval(role, TIER_EDGE)
    if decision.decision != PolicyDecision.ALLOW:
        return {
            "ok": False,
            "reason": decision.reason,
            "ticket_id": (ticket_id or "").strip(),
            "live_yaml_written": False,
        }

    tid = (ticket_id or "").strip()
    rows = _read_all()
    found = None
    idx = -1
    for i, row in enumerate(rows):
        if row.get("ticket_id") == tid:
            found = dict(row)
            idx = i
            break
    if found is None:
        return {"ok": False, "reason": "not_found", "ticket_id": tid}
    if found.get("edge_rolled_back"):
        return {"ok": True, "idempotent": True, "ticket": found, "edge_written": False}
    before = found.get("edge_before")
    if not isinstance(before, dict) or "left" not in before or "right" not in before:
        return {"ok": False, "reason": "edge_before_missing", "ticket_id": tid, "edge_written": False}
    if found.get("decision") != "merge" or not found.get("edge_written"):
        return {"ok": False, "reason": "edge_not_written", "ticket_id": tid, "edge_written": False}

    left_domain = str(found.get("left_domain") or "")
    right_domain = str(found.get("right_domain") or "")
    left_id = str(found.get("left_id") or "")
    right_id = str(found.get("right_id") or "")
    try:
        left_now = _read_cross_domain(left_domain, left_id)
        right_now = _read_cross_domain(right_domain, right_id)
    except Exception:
        logger.warning("edge rollback read failed", exc_info=True)
        return {"ok": False, "reason": "edge_restore_failed", "ticket_id": tid}
    if not _points_at(left_now, right_id, right_domain) or not _points_at(right_now, left_id, left_domain):
        return {"ok": False, "reason": "edge_superseded", "ticket_id": tid, "edge_written": True}

    if not _restore_cross_domain(left_domain, left_id, before.get("left")):
        return {"ok": False, "reason": "edge_restore_failed", "ticket_id": tid}
    if not _restore_cross_domain(right_domain, right_id, before.get("right")):
        _restore_cross_domain(left_domain, left_id, left_now)
        return {"ok": False, "reason": "edge_restore_failed", "ticket_id": tid}

    found.update(
        {
            "edge_rolled_back": True,
            "edge_written": False,
            "rollback_role": (role or "").strip(),
            "rolled_back_at": time.time(),
            "updated_at": time.time(),
        }
    )
    rows[idx] = found
    _rewrite(rows)
    return {
        "ok": True,
        "idempotent": False,
        "ticket": found,
        "edge_written": False,
        "live_yaml_written": False,
    }


def is_approved_for_resolve(ticket_id: str) -> bool:
    row = get_ticket(ticket_id)
    return bool(
        row
        and row.get("status") == "approved"
        and row.get("decision") == "merge"
    )
