"""H5 — skill draft pack. Human approval lists it. Never auto-lists, never writes SKILL.md."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_APPROVE_ROLES = frozenset({"admin"})


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def drafts_dir() -> Path:
    return _home() / "org" / "skill_drafts"


def _draft_path(draft_id: str) -> Path:
    safe = "".join(ch for ch in draft_id if ch.isalnum() or ch in "-_")[:80]
    return drafts_dir() / f"{safe}.json"


def _write(doc: Dict[str, Any]) -> None:
    path = _draft_path(str(doc.get("draft_id") or ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _read(draft_id: str) -> Optional[Dict[str, Any]]:
    path = _draft_path(draft_id)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("h5 draft unreadable: %s", path, exc_info=True)
        return None
    return raw if isinstance(raw, dict) else None


def list_skill_candidates(*, domain_id: str) -> List[Dict[str, Any]]:
    from core.harness.knowledge.ontology_case_learning import OntologyCaseStore

    did = (domain_id or "").strip() or "it-ops"
    items: List[Dict[str, Any]] = []
    for case in OntologyCaseStore(did)._load().values():
        meta = case.metadata or {}
        if not meta.get("skill_candidate"):
            continue
        items.append(
            {
                "case_id": case.case_id,
                "domain_id": case.domain_id,
                "title": case.title,
                "summary": (case.summary or "")[:400],
                "trace_id": str(meta.get("trace_id") or ""),
            }
        )
    return items


def list_skill_drafts(*, role: str, domain_id: str = "") -> Dict[str, Any]:
    if not (role or "").strip():
        return {"ok": False, "reason": "identity_missing", "writable": False}
    did = (domain_id or "").strip()
    rows: List[Dict[str, Any]] = []
    root = drafts_dir()
    if root.is_dir():
        for path in sorted(root.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            if did and str(raw.get("domain_id") or "") != did:
                continue
            rows.append(raw)
    return {
        "ok": True,
        "writable": False,
        "items": rows,
        "candidates": list_skill_candidates(domain_id=did or "it-ops"),
        "auto_listed": False,
        "m4_claim_allowed": False,
        "authority_note": "草稿不是上架。人批后才登记市场。不写 SKILL.md。",
    }


def create_skill_draft(*, role: str, case_id: str, domain_id: str = "it-ops") -> Dict[str, Any]:
    if not (role or "").strip():
        return {"ok": False, "reason": "identity_missing", "writable": False}
    cid = (case_id or "").strip()
    if not cid:
        return {"ok": False, "reason": "case_missing", "writable": False}
    did = (domain_id or "").strip() or "it-ops"
    match = next((c for c in list_skill_candidates(domain_id=did) if c["case_id"] == cid), None)
    if not match:
        return {"ok": False, "reason": "not_candidate", "writable": False, "listed": False}
    draft_id = f"h5-{cid}"[:80]
    existing = _read(draft_id)
    if existing and existing.get("status") == "listed":
        return {**existing, "ok": True, "already": True, "auto_listed": False}
    doc = {
        "draft_id": draft_id,
        "case_id": cid,
        "domain_id": did,
        "title": match["title"],
        "summary": match["summary"],
        "status": "draft",
        "listed": False,
        "skill_id": "",
        "created_at": time.time(),
        "auto_listed": False,
        "wrote_skill_md": False,
        "m4_claim_allowed": False,
    }
    _write(doc)
    return {"ok": True, "writable": False, **doc}


def _default_register(skill_id: str, name: str, description: str) -> bool:
    from core.api.core_facade import get_skill_marketplace

    return bool(
        get_skill_marketplace().register(
            skill_id,
            name,
            description,
            category="org-h5",
            tags=["h5", "human_approved"],
        )
    )


def approve_skill_draft(
    *,
    role: str,
    draft_id: str,
    register_fn: Optional[Callable[[str, str, str], bool]] = None,
) -> Dict[str, Any]:
    role_n = (role or "").strip().lower()
    if not role_n:
        return {"ok": False, "reason": "identity_missing", "writable": False}
    if role_n not in _APPROVE_ROLES:
        return {"ok": False, "reason": "approve_forbidden", "writable": False}
    doc = _read(draft_id)
    if not doc:
        return {"ok": False, "reason": "not_found", "writable": False}
    if doc.get("status") == "listed":
        return {"ok": True, "already": True, "listed": True, "auto_listed": False, **doc}
    if doc.get("status") != "draft":
        return {"ok": False, "reason": "not_draft", "writable": False, "status": doc.get("status")}
    skill_id = f"h5.{doc.get('domain_id')}.{doc.get('case_id')}"[:120]
    name = str(doc.get("title") or skill_id)[:200]
    description = str(doc.get("summary") or "")[:1000]
    fn = register_fn or _default_register
    try:
        ok = bool(fn(skill_id, name, description))
    except Exception:
        logger.warning("h5 marketplace register failed", exc_info=True)
        return {"ok": False, "reason": "register_failed", "listed": False, "writable": False}
    if not ok:
        return {"ok": False, "reason": "register_failed", "listed": False, "writable": False}
    doc["status"] = "listed"
    doc["listed"] = True
    doc["skill_id"] = skill_id
    doc["approved_by"] = role_n
    doc["approved_at"] = time.time()
    doc["auto_listed"] = False
    doc["wrote_skill_md"] = False
    _write(doc)
    return {"ok": True, "writable": False, **doc}


def reject_skill_draft(*, role: str, draft_id: str) -> Dict[str, Any]:
    role_n = (role or "").strip().lower()
    if not role_n:
        return {"ok": False, "reason": "identity_missing", "writable": False}
    if role_n not in _APPROVE_ROLES:
        return {"ok": False, "reason": "approve_forbidden", "writable": False}
    doc = _read(draft_id)
    if not doc:
        return {"ok": False, "reason": "not_found", "writable": False}
    if doc.get("status") == "listed":
        return {"ok": False, "reason": "already_listed", "writable": False}
    doc["status"] = "rejected"
    doc["listed"] = False
    doc["auto_listed"] = False
    _write(doc)
    return {"ok": True, "writable": False, **doc}


def list_action_gap_hints(*, domain_id: str = "it-ops") -> Dict[str, Any]:
    """Same action failed at least twice. Hint only. Does not open a write path."""
    from core.harness.knowledge.ontology_case_learning import OntologyCaseStore

    did = (domain_id or "").strip() or "it-ops"
    buckets: Dict[str, List[str]] = {}
    for case in OntologyCaseStore(did)._load().values():
        if case.outcome == "success":
            continue
        if case.outcome != "failure" and not (case.metadata or {}).get("schema_gap"):
            continue
        aid = (case.action_id or "").strip() or "unknown"
        buckets.setdefault(aid, []).append(case.case_id)
    items = []
    for aid, ids in sorted(buckets.items()):
        if len(ids) < 2:
            continue
        items.append(
            {
                "action_id": aid,
                "failure_count": len(ids),
                "can_draft_proposal": True,
                "wrote_live_yaml": False,
                "hint": "同一动作连续失败。可走既有提案人批。本接口不写 YAML。",
            }
        )
    return {
        "ok": True,
        "domain_id": did,
        "items": items,
        "wrote_live_yaml": False,
        "m4_claim_allowed": False,
    }


def assemble_skill_bundle(*, role: str, draft_ids: List[str]) -> Dict[str, Any]:
    """Pack existing drafts into one bundle. Does not list or write SKILL.md."""
    if not (role or "").strip():
        return {"ok": False, "reason": "identity_missing", "writable": False}
    ids = [str(i).strip() for i in (draft_ids or []) if str(i).strip()]
    if not ids:
        return {"ok": False, "reason": "drafts_missing", "writable": False}
    members = []
    for did in ids[:8]:
        doc = _read(did)
        if not doc or doc.get("status") == "rejected":
            return {"ok": False, "reason": "draft_not_usable", "draft_id": did, "writable": False}
        members.append(
            {"draft_id": doc.get("draft_id"), "title": doc.get("title"), "status": doc.get("status")}
        )
    bundle_id = ("bundle-" + "-".join(ids))[:70]
    bundle = {
        "draft_id": bundle_id,
        "kind": "bundle",
        "members": members,
        "status": "draft",
        "listed": False,
        "auto_listed": False,
        "wrote_skill_md": False,
        "m4_claim_allowed": False,
        "created_at": time.time(),
        "authority_note": "只组装已有草稿。不生成 SKILL.md。人批后才可登记。",
    }
    _write(bundle)
    return {"ok": True, "writable": False, **bundle}
