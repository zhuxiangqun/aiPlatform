u"""
Ontology Approval Manager — 本体变更审批工作流 (v2.8).

Manages change request lifecycle: submit → review → approve/reject.
Integrates with publish_ontology_domain() for pre-publish gate checking.
"""
from __future__ import annotations

import logging
import os as _os
import sqlite3 as _sqlite3
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ontology_approval")

DB_PATH = _os.path.expanduser("~/.aiplat/state_changes.db")


@dataclass
class ChangeRequest:
    id: str
    domain_id: str
    change_type: str
    diff_json: str = ""
    requested_by: str = ""
    justification: str = ""
    status: str = "pending"
    approved_by: str = ""
    approved_at: float = 0.0
    rejected_by: str = ""
    rejected_at: float = 0.0
    rejection_reason: str = ""
    requested_at: float = 0.0


def _ensure_schema():
    conn = _sqlite3.connect(DB_PATH, timeout=5.0)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS change_requests (
            id TEXT PRIMARY KEY,
            domain_id TEXT NOT NULL,
            change_type TEXT NOT NULL,
            diff_json TEXT DEFAULT '',
            requested_by TEXT DEFAULT '',
            justification TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            approved_by TEXT DEFAULT '',
            approved_at REAL DEFAULT 0,
            rejected_by TEXT DEFAULT '',
            rejected_at REAL DEFAULT 0,
            rejection_reason TEXT DEFAULT '',
            requested_at REAL NOT NULL DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cr_domain ON change_requests(domain_id, status)")
    conn.commit()
    conn.close()


def submit(
    domain_id: str,
    change_type: str,
    *,
    diff: Dict[str, Any] = None,
    requested_by: str = "system",
    justification: str = "",
) -> ChangeRequest:
    u"""Submit a change request for approval."""
    import json
    _ensure_schema()
    rid = f"cr-{domain_id}-{int(_time.time() * 1000)}"
    now = _time.time()
    diff_str = json.dumps(diff or {}, ensure_ascii=False)

    conn = _sqlite3.connect(DB_PATH, timeout=5.0)
    conn.execute(
        "INSERT INTO change_requests (id, domain_id, change_type, diff_json, requested_by, justification, status, requested_at) VALUES (?,?,?,?,?,?,?,?)",
        (rid, domain_id, change_type, diff_str, requested_by, justification, "pending", now),
    )
    conn.commit()
    conn.close()

    logger.info("Change request submitted: %s (%s by %s)", rid, change_type, requested_by)
    return ChangeRequest(
        id=rid, domain_id=domain_id, change_type=change_type,
        diff_json=diff_str, requested_by=requested_by, justification=justification,
        status="pending", requested_at=now,
    )


def approve(request_id: str, approved_by: str, comment: str = "") -> Dict[str, Any]:
    u"""Approve a change request."""
    _ensure_schema()
    conn = _sqlite3.connect(DB_PATH, timeout=5.0)
    row = conn.execute("SELECT id, status FROM change_requests WHERE id = ?", (request_id,)).fetchone()
    if not row:
        conn.close()
        return {"success": False, "error": "Request not found"}
    if row[1] != "pending":
        conn.close()
        return {"success": False, "error": f"Request is {row[1]}, not pending"}

    now = _time.time()
    conn.execute(
        "UPDATE change_requests SET status = ?, approved_by = ?, approved_at = ? WHERE id = ?",
        ("approved", approved_by, now, request_id),
    )
    conn.commit()
    conn.close()
    logger.info("Change request approved: %s by %s", request_id, approved_by)
    return {"success": True, "request_id": request_id, "status": "approved"}


def reject(request_id: str, rejected_by: str, reason: str = "") -> Dict[str, Any]:
    u"""Reject a change request."""
    _ensure_schema()
    conn = _sqlite3.connect(DB_PATH, timeout=5.0)
    row = conn.execute("SELECT id, status FROM change_requests WHERE id = ?", (request_id,)).fetchone()
    if not row:
        conn.close()
        return {"success": False, "error": "Request not found"}

    now = _time.time()
    conn.execute(
        "UPDATE change_requests SET status = ?, rejected_by = ?, rejected_at = ?, rejection_reason = ? WHERE id = ?",
        ("rejected", rejected_by, now, reason, request_id),
    )
    conn.commit()
    conn.close()
    logger.info("Change request rejected: %s by %s (%s)", request_id, rejected_by, reason)
    return {"success": True, "request_id": request_id, "status": "rejected"}


def list_pending(domain_id: str = "") -> List[Dict[str, Any]]:
    u"""List pending change requests."""
    _ensure_schema()
    conn = _sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = _sqlite3.Row
    if domain_id:
        rows = conn.execute(
            "SELECT * FROM change_requests WHERE status = 'pending' AND domain_id = ? ORDER BY requested_at DESC",
            (domain_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM change_requests WHERE status = 'pending' ORDER BY requested_at DESC",
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_history(domain_id: str = "", limit: int = 50) -> List[Dict[str, Any]]:
    u"""Get approval history."""
    _ensure_schema()
    conn = _sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = _sqlite3.Row
    if domain_id:
        rows = conn.execute(
            "SELECT * FROM change_requests WHERE domain_id = ? ORDER BY requested_at DESC LIMIT ?",
            (domain_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM change_requests ORDER BY requested_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def can_publish(user_role: str = "") -> bool:
    u"""Check if the user role can publish ontology changes."""
    role = (user_role or "").lower()
    return role in {"governance_admin", "admin", "operator"}
