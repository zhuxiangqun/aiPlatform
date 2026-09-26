"""Phase K5 — repeated failures become edge proposals. Never auto-apply.

Aggregation key: domain_id + action_id + error_code.
Threshold: >=3 in window, or >=2 with mean reward_ema below the existing evolve floor.
Open drafts are not duplicated. Drafts older than 30 days expire without apply.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_WINDOW_SEC = 30 * 86400
_EXPIRE_SEC = 30 * 86400


def _home() -> Path:
    import os

    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def ledger_path() -> Path:
    return _home() / "k_wave" / "k5_proposals.jsonl"


def _read() -> List[Dict[str, Any]]:
    path = ledger_path()
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
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _expire(rows: List[Dict[str, Any]], *, now: float) -> List[Dict[str, Any]]:
    out = []
    for row in rows:
        fresh = dict(row)
        created = float(fresh.get("created_at") or 0)
        if (
            fresh.get("status") in ("draft", "open")
            and created
            and (now - created) >= _EXPIRE_SEC
            and not fresh.get("applied")
        ):
            fresh["status"] = "expired"
            fresh["auto_apply"] = False
            fresh["expired_at"] = now
        out.append(fresh)
    return out


def _error_code(case: Any) -> str:
    meta = case.metadata if isinstance(case.metadata, dict) else {}
    code = str(meta.get("error_code") or "").strip()
    if code:
        return code
    reasons = meta.get("exception_reasons") or []
    if isinstance(reasons, list) and reasons:
        return str(reasons[0] or "").strip()
    if str(case.outcome or "") == "failure":
        return "failure"
    return ""


def _class_name(action_id: str) -> str:
    raw = (action_id or "RepeatFail").split(":")[-1]
    safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in raw)[:40] or "RepeatFail"
    return f"RepeatFail_{safe}"[:64]


def _groups(domain_id: str, *, now: float) -> Dict[str, Dict[str, Any]]:
    from core.harness.knowledge.ontology_case_learning import OntologyCaseStore, _evolve_min_reward

    store = OntologyCaseStore(domain_id)
    groups: Dict[str, Dict[str, Any]] = {}
    floor = _evolve_min_reward()
    for case in store._load().values():
        if str(case.domain_id or domain_id) != domain_id:
            continue
        if str(case.outcome or "") not in ("failure", "partial"):
            continue
        if float(case.created_at or 0) and (now - float(case.created_at)) > _WINDOW_SEC:
            continue
        action = str(case.action_id or "").strip()
        err = _error_code(case)
        if not action or not err:
            continue
        key = f"{domain_id}|{action}|{err}"
        bucket = groups.setdefault(
            key,
            {
                "key": key,
                "domain_id": domain_id,
                "action_id": action,
                "error_code": err,
                "case_ids": [],
                "reward_sum": 0.0,
                "n": 0,
            },
        )
        bucket["case_ids"].append(case.case_id)
        bucket["reward_sum"] += float(case.reward_ema or 0)
        bucket["n"] += 1
        meta = case.metadata if isinstance(case.metadata, dict) else {}
        tid = str(meta.get("trace_id") or "").strip()
        if tid:
            seen = bucket.setdefault("trace_ids", [])
            if tid not in seen:
                seen.append(tid)
    for bucket in groups.values():
        n = bucket["n"]
        mean = bucket["reward_sum"] / n if n else 1.0
        bucket["reward_mean"] = mean
        bucket["min_reward"] = floor
        bucket["hit"] = n >= 3 or (n >= 2 and mean < floor)
    return groups


def _open_keys(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    found: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if row.get("status") in ("draft", "open") and not row.get("applied"):
            found[str(row.get("dedup_key") or "")] = row
    return found


async def enqueue_repeat_failure_proposals(
    domain_id: str = "it-ops",
    *,
    writer: Optional[Callable[..., Any]] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Scan cases and enqueue edge-class drafts. auto_apply stays false."""
    from core.apps.fde.service.v_wave_guard import edge_auto_apply_block

    blocked = edge_auto_apply_block()
    if blocked:
        return blocked
    did = (domain_id or "").strip() or "it-ops"
    clock = now if now is not None else time.time()
    rows = _expire(_read(), now=clock)
    open_keys = _open_keys(rows)
    groups = _groups(did, now=clock)
    created: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    async def _write(changes: Dict[str, Any]) -> str:
        if writer is not None:
            result = writer(did, changes)
            if hasattr(result, "__await__"):
                result = await result
            return str(result or "")
        from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore

        return await VersionedOntologyStore(did).create_proposal(changes, author="k5-repeat-failure")

    for key, bucket in groups.items():
        if not bucket.get("hit"):
            skipped.append({"key": key, "reason": "below_threshold", "n": bucket["n"]})
            continue
        if key in open_keys:
            skipped.append({"key": key, "reason": "open_draft", "proposal_id": open_keys[key].get("proposal_id")})
            continue
        class_name = _class_name(bucket["action_id"])
        changes = {
            "add": {
                "class": {
                    "name": class_name,
                    "label": class_name,
                    "tier": "edge",
                    "required_fields": ["name"],
                    "description": (
                        f"K5 draft from repeated {bucket['action_id']} / {bucket['error_code']} "
                        f"n={bucket['n']} cases={','.join(bucket['case_ids'][:8])}"
                    ),
                }
            },
            "source": {
                "kind": "k5_repeat_failure",
                "dedup_key": key,
                "auto_apply": False,
                "policy_gate": False,
            },
        }
        proposal_id = ""
        status = "draft"
        try:
            proposal_id = await _write(changes)
        except Exception:
            logger.warning("K5 proposal writer failed", exc_info=True)
            proposal_id = f"k5_local_{uuid.uuid4().hex[:10]}"
            status = "local_draft"
        event = {
            "proposal_id": proposal_id,
            "dedup_key": key,
            "domain_id": did,
            "action_id": bucket["action_id"],
            "error_code": bucket["error_code"],
            "case_ids": bucket["case_ids"],
            "n": bucket["n"],
            "class_name": class_name,
            "tier": "edge",
            "status": status,
            "auto_apply": False,
            "applied": False,
            "created_at": clock,
            "authority_note": "K5 draft only; human approve→apply; not a PolicyGate change",
        }
        shared = bucket.get("trace_ids") or []
        if len(shared) == 1:
            event["trace_id"] = shared[0]
            event["trace_origin"] = "inherited"
        rows.append(event)
        created.append(event)
        open_keys[key] = event

    _rewrite(rows)
    return {
        "status": "ok",
        "domain_id": did,
        "created": created,
        "skipped": skipped,
        "auto_apply": False,
        "created_count": len(created),
    }


def _gap_change(case: Any, *, class_name: str) -> Dict[str, Any]:
    return {
        "add": {
            "class": {
                "name": class_name,
                "label": class_name,
                "tier": "edge",
                "required_fields": ["name"],
                "description": f"Schema gap draft from {case.case_id}",
            }
        },
        "source": {"kind": "schema_gap", "case_id": case.case_id, "auto_apply": False},
    }


def preview_schema_gaps(domain_id: str = "it-ops", *, limit: int = 5) -> Dict[str, Any]:
    """Read-only Diff for schema_gap cases. Does not create proposals or write YAML."""
    from core.harness.knowledge.ontology_case_learning import OntologyCaseStore
    from core.harness.knowledge.versioned_ontology_store import (
        VersionedOntologyStore,
        json_change_diff,
        project_ontology_changes,
    )

    did = (domain_id or "").strip() or "it-ops"
    cap = max(1, min(int(limit or 5), 8))
    clock = time.time()
    open_keys = _open_keys(_expire(_read(), now=clock))
    current = VersionedOntologyStore(did).load_current()
    items: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for case in OntologyCaseStore(did)._load().values():
        if len(items) >= cap:
            break
        meta = case.metadata if isinstance(case.metadata, dict) else {}
        if not meta.get("schema_gap"):
            continue
        key = f"gap|{did}|{case.case_id}"
        if key in open_keys:
            skipped.append({"key": key, "reason": "open_draft", "proposal_id": open_keys[key].get("proposal_id")})
            continue
        class_name = _class_name(str(case.action_id or "SchemaGap"))
        changes = _gap_change(case, class_name=class_name)
        projected = project_ontology_changes(current, changes)
        items.append(
            {
                "case_id": case.case_id,
                "action_id": case.action_id,
                "class_name": class_name,
                "dedup_key": key,
                "changes": changes,
                "diff": json_change_diff(current, projected),
            }
        )

    return {
        "ok": True,
        "domain_id": did,
        "items": items,
        "skipped": skipped,
        "item_count": len(items),
        "auto_apply": False,
        "applied": False,
        "wrote_live_yaml": False,
        "m4_claim_allowed": False,
        "authority_note": "缺口 Diff 预览。确认后才进提案账本。本调用不写活 YAML。",
    }


async def draft_schema_gaps(
    domain_id: str = "it-ops",
    *,
    writer: Optional[Callable[..., Any]] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """One edge draft per schema_gap case. Same ledger as K5. Never applies."""
    from core.apps.fde.service.v_wave_guard import edge_auto_apply_block
    from core.harness.knowledge.ontology_case_learning import OntologyCaseStore

    blocked = edge_auto_apply_block()
    if blocked:
        return blocked
    did = (domain_id or "").strip() or "it-ops"
    cap = max(1, min(int(limit or 5), 8))
    clock = time.time()
    rows = _expire(_read(), now=clock)
    open_keys = _open_keys(rows)
    created: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    async def _write(changes: Dict[str, Any]) -> str:
        if writer is not None:
            result = writer(did, changes)
            if hasattr(result, "__await__"):
                result = await result
            return str(result or "")
        from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore

        return await VersionedOntologyStore(did).create_proposal(changes, author="schema-gap")

    for case in OntologyCaseStore(did)._load().values():
        if len(created) >= cap:
            break
        meta = case.metadata if isinstance(case.metadata, dict) else {}
        if not meta.get("schema_gap"):
            continue
        key = f"gap|{did}|{case.case_id}"
        if key in open_keys:
            skipped.append({"key": key, "reason": "open_draft", "proposal_id": open_keys[key].get("proposal_id")})
            continue
        class_name = _class_name(str(case.action_id or "SchemaGap"))
        changes = _gap_change(case, class_name=class_name)
        status = "draft"
        try:
            proposal_id = await _write(changes)
        except Exception:
            logger.warning("schema gap draft writer failed", exc_info=True)
            proposal_id = f"k5_local_{uuid.uuid4().hex[:10]}"
            status = "local_draft"
        event = {
            "proposal_id": proposal_id,
            "dedup_key": key,
            "domain_id": did,
            "action_id": case.action_id,
            "case_ids": [case.case_id],
            "class_name": class_name,
            "tier": "edge",
            "status": status,
            "auto_apply": False,
            "applied": False,
            "created_at": clock,
            "authority_note": "缺口草稿。走人批 apply。本调用不写活 YAML。",
        }
        rows.append(event)
        created.append(event)
        open_keys[key] = event

    if created:
        _rewrite(rows)
    return {
        "ok": True,
        "domain_id": did,
        "created": created,
        "skipped": skipped,
        "created_count": len(created),
        "auto_apply": False,
        "applied": False,
        "wrote_live_yaml": False,
        "m4_claim_allowed": False,
    }
