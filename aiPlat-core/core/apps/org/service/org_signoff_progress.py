"""S4 — signoff progress. Recordable; never flips m4_claim_allowed."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

_WRITE_ROLES = frozenset({"admin"})


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def progress_path() -> Path:
    return _home() / "org" / "signoff_progress.json"


def default_progress() -> Dict[str, Any]:
    return {
        "oncall_name": "",
        "oncall_contact": "",
        "rollback_owner": "",
        "rollback_drill_done": False,
        "rollback_drill_at": "",
        "rollback_drill_notes": "",
        "intent_recorded": False,
        "dual_sign": [],
        "updated_at": 0,
        "m4_claim_allowed": False,
    }


def load_signoff_progress() -> Dict[str, Any]:
    path = progress_path()
    base = default_progress()
    if not path.is_file():
        return base
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("signoff progress unreadable", exc_info=True)
        return base
    if not isinstance(raw, dict):
        return base
    base.update({k: raw.get(k, base[k]) for k in base})
    base["m4_claim_allowed"] = False
    if not isinstance(base.get("dual_sign"), list):
        base["dual_sign"] = []
    return base


def get_signoff_progress(*, role: str) -> Dict[str, Any]:
    if not (role or "").strip():
        return {"ok": False, "reason": "identity_missing", "writable": False}
    prog = load_signoff_progress()
    oncall_ok = bool(str(prog.get("oncall_name") or "").strip()) and bool(
        str(prog.get("oncall_contact") or "").strip()
    )
    rollback_drill_ok = bool(prog.get("rollback_drill_done"))
    return {
        "ok": True,
        "writable": False,
        "m4_claim_allowed": False,
        "oncall_ok": oncall_ok,
        "rollback_drill_ok": rollback_drill_ok,
        **prog,
        "authority_note": "进度可记录。不是客户已签收。m4_claim_allowed 恒 false。",
    }


def save_signoff_progress(*, role: str, body: Dict[str, Any]) -> Dict[str, Any]:
    role_n = (role or "").strip().lower()
    if not role_n:
        return {"ok": False, "reason": "identity_missing", "writable": False}
    if role_n not in _WRITE_ROLES:
        return {"ok": False, "reason": "write_forbidden", "writable": False}
    cur = load_signoff_progress()
    if "oncall_name" in body:
        cur["oncall_name"] = str(body.get("oncall_name") or "")[:120]
    if "oncall_contact" in body:
        cur["oncall_contact"] = str(body.get("oncall_contact") or "")[:200]
    if "rollback_owner" in body:
        cur["rollback_owner"] = str(body.get("rollback_owner") or "")[:120]
    if "rollback_drill_done" in body:
        cur["rollback_drill_done"] = bool(body.get("rollback_drill_done"))
        if cur["rollback_drill_done"] and not str(cur.get("rollback_drill_at") or "").strip():
            cur["rollback_drill_at"] = time.strftime("%Y-%m-%d")
    if "rollback_drill_at" in body:
        cur["rollback_drill_at"] = str(body.get("rollback_drill_at") or "")[:40]
    if "rollback_drill_notes" in body:
        cur["rollback_drill_notes"] = str(body.get("rollback_drill_notes") or "")[:400]
    if "intent_recorded" in body:
        cur["intent_recorded"] = bool(body.get("intent_recorded"))
    if "dual_sign" in body and isinstance(body.get("dual_sign"), list):
        rows = []
        for row in body["dual_sign"][:12]:
            if not isinstance(row, dict):
                continue
            rows.append(
                {
                    "item": str(row.get("item") or "")[:200],
                    "customer": str(row.get("customer") or "")[:80],
                    "platform": str(row.get("platform") or "")[:80],
                    "date": str(row.get("date") or "")[:40],
                    "notes": str(row.get("notes") or "")[:200],
                }
            )
        cur["dual_sign"] = rows
    cur["updated_at"] = time.time()
    cur["m4_claim_allowed"] = False
    path = progress_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    return get_signoff_progress(role=role)
