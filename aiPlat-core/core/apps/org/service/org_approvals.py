"""H1 — approval inbox and snapshots. Read-only. Does not approve or write."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

KINDS = frozenset({"extraction", "arbitration", "proposal", "hitl"})
_ABSENT = "该信息未发生"
_FULL_VIEW = frozenset({"admin", "approver"})
_MAX_LIMIT = 50
_DEFAULT_LIMIT = 20


def _mask(text: str, *, full: bool) -> str:
    raw = (text or "").strip()
    if not raw:
        return _ABSENT
    if full:
        return raw[:2000]
    if len(raw) <= 8:
        return "***"
    return raw[:4] + "…" + "***"


def _paginate(items: List[Dict[str, Any]], *, offset: int, limit: int) -> Dict[str, Any]:
    off = max(0, int(offset or 0))
    lim = min(_MAX_LIMIT, max(1, int(limit or _DEFAULT_LIMIT)))
    slice_ = items[off : off + lim]
    return {
        "items": slice_,
        "offset": off,
        "limit": lim,
        "total": len(items),
        "has_more": off + lim < len(items),
    }


def _role_ok(role: str) -> Tuple[bool, str]:
    role_n = (role or "").strip().lower()
    if not role_n:
        return False, "identity_missing"
    return True, role_n


def _full_view(role_n: str) -> bool:
    return role_n in _FULL_VIEW


async def _list_extractions(domain_id: str) -> List[Dict[str, Any]]:
    try:
        from core.harness.knowledge_pipeline.extractor import PendingExtractionStore

        rows = await PendingExtractionStore().list_pending(domain_id or "it-ops")
    except Exception:
        logger.debug("approval inbox: extractions unavailable", exc_info=True)
        return []
    out: List[Dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "kind": "extraction",
                "id": str(row.get("extraction_id") or ""),
                "title": f"抽取 {(row.get('source_doc') or '')}"[:120] or "抽取待确认",
                "status": str(row.get("status") or "pending"),
                "domain_id": str(row.get("domain_id") or domain_id or ""),
                "trace_id": "",
                "created_at": str(row.get("created_at") or ""),
                "summary": f"entities={row.get('entity_count') or 0} conf={row.get('overall_confidence')}",
            }
        )
    return out


def _list_arbitration(domain_id: str) -> List[Dict[str, Any]]:
    from core.apps.fde.service.k_wave_arbit import list_tickets

    listed = list_tickets(status="pending", domain_id=domain_id or "it-ops")
    out: List[Dict[str, Any]] = []
    for row in listed.get("items") or []:
        out.append(
            {
                "kind": "arbitration",
                "id": str(row.get("ticket_id") or ""),
                "title": f"仲裁 {row.get('left_id')}↔{row.get('right_id')}",
                "status": str(row.get("status") or "pending"),
                "domain_id": str(row.get("left_domain") or row.get("domain_id") or domain_id or ""),
                "trace_id": str(row.get("trace_id") or ""),
                "created_at": str(row.get("created_at") or row.get("updated_at") or ""),
                "summary": f"strategy={row.get('strategy')} conf={row.get('confidence')}",
            }
        )
    return out


async def _list_proposals(domain_id: str) -> List[Dict[str, Any]]:
    try:
        from core.harness.infrastructure.action_store import ActionStore

        store = ActionStore()
        await store.initialize()
        rows = await store.list_ontology_proposals(domain_id or "it-ops")
    except Exception:
        logger.debug("approval inbox: proposals unavailable", exc_info=True)
        return []
    out: List[Dict[str, Any]] = []
    for row in rows:
        status = str(row.get("status") or "")
        if status not in ("draft", "pending"):
            continue
        impact = {}
        try:
            impact = json.loads(row.get("impact_analysis") or "{}") or {}
        except Exception:
            impact = {}
        source_kind = ""
        try:
            raw_ch = row.get("changes") or "{}"
            ch = json.loads(raw_ch) if isinstance(raw_ch, str) else (raw_ch or {})
            source_kind = str((ch.get("source") or {}).get("kind") or "")
        except Exception:
            source_kind = ""
        tier = impact.get("max_tier") or row.get("max_tier") or "—"
        summary = f"tier={tier}"
        if source_kind:
            summary = f"{summary} · {source_kind}"
        out.append(
            {
                "kind": "proposal",
                "id": str(row.get("proposal_id") or ""),
                "title": f"提案 {row.get('proposal_id')}",
                "status": status,
                "domain_id": str(row.get("domain_id") or domain_id or ""),
                "trace_id": str(impact.get("trace_id") or row.get("trace_id") or ""),
                "created_at": str(row.get("created_at") or ""),
                "summary": summary,
                "source_kind": source_kind or _ABSENT,
            }
        )
    return out


def _list_hitl(domain_id: str, goal_id: str) -> List[Dict[str, Any]]:
    from core.apps.org.service.org_kpi import weekly_kpi_report

    gid = (goal_id or "").strip() or "goal-it-ops-alert-sla"
    weekly = weekly_kpi_report(domain_id or "it-ops", gid, week="")
    out: List[Dict[str, Any]] = []
    for row in weekly.get("pending_hitl") or []:
        rid = str(row.get("run_id") or "")
        out.append(
            {
                "kind": "hitl",
                "id": rid,
                "title": f"HITL {rid}",
                "status": "needs_hitl",
                "domain_id": domain_id or "it-ops",
                "trace_id": rid,
                "created_at": str(row.get("started_at") or ""),
                "summary": f"ticket={row.get('hitl_ticket_id') or _ABSENT}",
            }
        )
    return out


async def list_approval_inbox(
    *,
    role: str,
    domain_id: str = "it-ops",
    goal_id: str = "goal-it-ops-alert-sla",
    kind: str = "",
    offset: int = 0,
    limit: int = _DEFAULT_LIMIT,
) -> Dict[str, Any]:
    ok, role_n = _role_ok(role)
    if not ok:
        return {"ok": False, "reason": role_n, "writable": False}

    want = (kind or "").strip().lower()
    if want and want not in KINDS:
        return {"ok": False, "reason": "invalid_kind", "writable": False}

    items: List[Dict[str, Any]] = []
    if not want or want == "extraction":
        items.extend(await _list_extractions(domain_id))
    if not want or want == "arbitration":
        items.extend(_list_arbitration(domain_id))
    if not want or want == "proposal":
        items.extend(await _list_proposals(domain_id))
    if not want or want == "hitl":
        items.extend(_list_hitl(domain_id, goal_id))

    items.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    page = _paginate(items, offset=offset, limit=limit)
    page.update(
        {
            "ok": True,
            "writable": False,
            "role": role_n,
            "full_view": _full_view(role_n),
            "authority_note": "只读待批列表。批准仍走既有路由。",
        }
    )
    return page


async def _snapshot_extraction(item_id: str, *, full: bool) -> Dict[str, Any]:
    try:
        from core.harness.knowledge_pipeline.extractor import PendingExtractionStore

        row = await PendingExtractionStore().get_row(item_id)
    except Exception:
        row = None
    if not row:
        return {"kind": "extraction", "id": item_id, "status": "absent", "note": _ABSENT}
    ents_raw = row.get("entities_json") or "[]"
    try:
        ents = json.loads(ents_raw) if isinstance(ents_raw, str) else ents_raw
    except Exception:
        ents = []
    source = _mask(str(row.get("source_doc") or ""), full=full)
    return {
        "kind": "extraction",
        "id": item_id,
        "status": str(row.get("status") or ""),
        "domain_id": row.get("domain_id"),
        "trace_id": _ABSENT,
        "confidence": row.get("overall_confidence"),
        "entity_count": row.get("entity_count"),
        "source_excerpt": source,
        "entities_preview": (ents or [])[:5] if full else _ABSENT,
        "draft_yaml_path": row.get("draft_yaml_path") if full else _ABSENT,
    }


def _snapshot_arbitration(item_id: str, *, full: bool) -> Dict[str, Any]:
    from core.apps.fde.service.k_wave_arbit import get_ticket

    row = get_ticket(item_id)
    if not row:
        return {"kind": "arbitration", "id": item_id, "status": "absent", "note": _ABSENT}
    return {
        "kind": "arbitration",
        "id": item_id,
        "status": row.get("status"),
        "decision": row.get("decision") or _ABSENT,
        "left_id": row.get("left_id"),
        "right_id": row.get("right_id"),
        "left_domain": row.get("left_domain"),
        "right_domain": row.get("right_domain"),
        "strategy": row.get("strategy"),
        "confidence": row.get("confidence"),
        "trace_id": row.get("trace_id") or _ABSENT,
        "edge_before": row.get("edge_before") if full else _ABSENT,
        "edge_written": row.get("edge_written"),
        "note": row.get("decision_note") if full else _mask(str(row.get("decision_note") or ""), full=False),
    }


async def _snapshot_proposal(item_id: str, *, full: bool) -> Dict[str, Any]:
    try:
        from core.harness.infrastructure.action_store import ActionStore

        store = ActionStore()
        await store.initialize()
        row = await store.get_ontology_proposal(item_id)
    except Exception:
        row = None
    if not row:
        return {"kind": "proposal", "id": item_id, "status": "absent", "note": _ABSENT}
    impact = {}
    try:
        impact = json.loads(row.get("impact_analysis") or "{}") or {}
    except Exception:
        impact = {}
    raw_changes = row.get("changes") or row.get("changes_json") or ""
    changes_obj: Dict[str, Any] = {}
    if isinstance(raw_changes, dict):
        changes_obj = raw_changes
    elif isinstance(raw_changes, str) and raw_changes.strip():
        try:
            parsed = json.loads(raw_changes)
            if isinstance(parsed, dict):
                changes_obj = parsed
        except Exception:
            changes_obj = {}
    changes_preview: Any = changes_obj if full else _mask(str(raw_changes)[:200], full=False)

    diff: Dict[str, Any] = {
        "kind": "json_diff",
        "count": 0,
        "changes": [],
        "wrote_live_yaml": False,
    }
    try:
        from core.harness.knowledge.versioned_ontology_store import (
            VersionedOntologyStore,
            json_change_diff,
            project_ontology_changes,
        )

        did = str(row.get("domain_id") or "it-ops")
        current = VersionedOntologyStore(did).load_current()
        projected = project_ontology_changes(current, changes_obj)
        full_diff = json_change_diff(current, projected)
        if full:
            diff = full_diff
        else:
            diff = {
                "kind": "json_diff",
                "count": int(full_diff.get("count") or 0),
                "changes": [{"path": c.get("path")} for c in (full_diff.get("changes") or [])[:12]],
                "redacted_values": True,
                "wrote_live_yaml": False,
            }
    except Exception:
        logger.debug("proposal snapshot diff failed", exc_info=True)

    source = changes_obj.get("source") if isinstance(changes_obj.get("source"), dict) else {}
    return {
        "kind": "proposal",
        "id": item_id,
        "status": row.get("status"),
        "domain_id": row.get("domain_id"),
        "trace_id": impact.get("trace_id") or row.get("trace_id") or _ABSENT,
        "max_tier": impact.get("max_tier") or _ABSENT,
        "case_ids": impact.get("case_ids") or source.get("case_id") or _ABSENT,
        "error_summary": impact.get("error_summary") or impact.get("bucket") or _ABSENT,
        "source_kind": source.get("kind") or _ABSENT,
        "changes_preview": changes_preview,
        "diff": diff,
        "wrote_live_yaml": False,
    }


def _snapshot_hitl(item_id: str, *, domain_id: str, full: bool) -> Dict[str, Any]:
    from core.apps.org.service.org_runtime import list_runs

    runs = list_runs("", limit=100).get("runs") or []
    found = None
    for r in runs:
        if str(r.get("run_id") or "") == item_id:
            found = r
            break
    if not found:
        return {"kind": "hitl", "id": item_id, "status": "absent", "note": _ABSENT}
    exceptions = found.get("exceptions") or []
    if not full:
        exceptions = [{"reason": _mask(str(e.get("reason") or ""), full=False)} for e in exceptions if isinstance(e, dict)]
    return {
        "kind": "hitl",
        "id": item_id,
        "status": found.get("status"),
        "domain_id": found.get("domain_id") or domain_id,
        "goal_id": found.get("goal_id"),
        "trace_id": found.get("trace_id") or item_id,
        "post_id": found.get("post_id") or _ABSENT,
        "steps_count": len(found.get("steps") or []),
        "exceptions": exceptions or _ABSENT,
        "week_label": found.get("week_label") or _ABSENT,
    }


async def get_approval_snapshot(
    kind: str,
    item_id: str,
    *,
    role: str,
    domain_id: str = "it-ops",
) -> Dict[str, Any]:
    ok, role_n = _role_ok(role)
    if not ok:
        return {"ok": False, "reason": role_n, "writable": False}
    k = (kind or "").strip().lower()
    iid = (item_id or "").strip()
    if k not in KINDS:
        return {"ok": False, "reason": "invalid_kind", "writable": False}
    if not iid:
        return {"ok": False, "reason": "id_required", "writable": False}

    full = _full_view(role_n)
    if k == "extraction":
        snap = await _snapshot_extraction(iid, full=full)
    elif k == "arbitration":
        snap = _snapshot_arbitration(iid, full=full)
    elif k == "proposal":
        snap = await _snapshot_proposal(iid, full=full)
    else:
        snap = _snapshot_hitl(iid, domain_id=domain_id or "it-ops", full=full)

    return {
        "ok": True,
        "writable": False,
        "role": role_n,
        "full_view": full,
        "redacted": not full,
        "snapshot": snap,
        "authority_note": "只读快照。批准走既有 confirm/decide/approve/apply 路由。",
    }
