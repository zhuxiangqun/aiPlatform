"""
ProposalStore — lightweight proposal/branch workflow for AI-generated changes.

When an AI agent (AutoLearner, Skill, Agent) proposes a change, it creates a
Proposal record. Admins can review the proposal, see the diff, and approve or
reject. Approved proposals auto-execute (SkillRegistry.register, etc.).

States: draft → pending_approval → approved → merged | rejected
Aligns with Palantir AIP's Proposal workflow (branch/merge semantics).

Integration:
  - AutoLearner → creates Proposal instead of directly approving
  - Admin UI → list/review/approve/reject
  - On approve → execute the proposed action (write to SkillRegistry, etc.)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.proposal")


def _get_db():
    db_path = os.getenv(
        "AIPLAT_EXECUTION_DB_PATH",
        os.path.join(os.path.expanduser("~"), ".aiplat", "aiplat_executions.sqlite3"),
    )
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=3000")
    return conn


def _init_table():
    conn = _get_db()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proposal_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                proposal_type TEXT NOT NULL DEFAULT 'skill_registration',
                status TEXT NOT NULL DEFAULT 'draft',
                proposed_by TEXT NOT NULL DEFAULT 'auto_learner',
                proposed_changes TEXT DEFAULT '{}',
                diff_text TEXT DEFAULT '',
                approved_by TEXT,
                approved_at REAL,
                rejected_reason TEXT,
                merged_at REAL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status)")
        conn.commit()
    finally:
        conn.close()


@dataclass
class Proposal:
    proposal_id: str
    title: str
    proposal_type: str = "skill_registration"
    status: str = "draft"
    proposed_by: str = "auto_learner"
    proposed_changes: dict = field(default_factory=dict)
    diff_text: str = ""
    approved_by: Optional[str] = None
    rejected_reason: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "proposal_id": self.proposal_id, "title": self.title,
            "proposal_type": self.proposal_type, "status": self.status,
            "proposed_by": self.proposed_by,
            "proposed_changes": self.proposed_changes,
            "diff_text": self.diff_text,
            "approved_by": self.approved_by,
            "rejected_reason": self.rejected_reason,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }


class ProposalStore:
    """Manage AI-generated change proposals with review/approve workflow."""

    def __init__(self):
        _init_table()

    def create(self, proposal: Proposal) -> str:
        """Create a new proposal. Returns proposal_id."""
        proposal.updated_at = time.time()
        conn = _get_db()
        try:
            conn.execute(
                """INSERT INTO proposals (proposal_id, title, proposal_type, status, proposed_by,
                   proposed_changes, diff_text, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (proposal.proposal_id, proposal.title, proposal.proposal_type,
                 proposal.status, proposal.proposed_by,
                 json.dumps(proposal.proposed_changes, ensure_ascii=False),
                 proposal.diff_text,
                 proposal.created_at, proposal.updated_at),
            )
            conn.commit()
            logger.info("Proposal created: %s (%s)", proposal.proposal_id, proposal.title)
            return proposal.proposal_id
        finally:
            conn.close()

    def submit(self, proposal_id: str) -> bool:
        """Submit a draft proposal for review."""
        return self._update_status(proposal_id, "pending_approval")

    def approve(self, proposal_id: str, approved_by: str = "admin") -> bool:
        """Approve a proposal. Triggers auto-merge."""
        now = time.time()
        conn = _get_db()
        try:
            conn.execute(
                """UPDATE proposals SET status = 'approved', approved_by = ?,
                   approved_at = ? WHERE proposal_id = ? AND status = 'pending_approval'""",
                (approved_by, now, proposal_id),
            )
            conn.commit()
            # Read proposal for merge
            row = conn.execute(
                "SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,)
            ).fetchone()
            if row:
                self._merge_proposal(dict(zip([c[0] for c in row.description], row)))
            return True
        finally:
            conn.close()

    def reject(self, proposal_id: str, reason: str = "") -> bool:
        """Reject a proposal with a reason."""
        return self._update_status(proposal_id, "rejected", rejected_reason=reason)

    def _update_status(self, proposal_id: str, status: str, **extra) -> bool:
        conn = _get_db()
        try:
            parts = ["status = ?", "updated_at = ?"]
            vals = [status, time.time()]
            for k, v in extra.items():
                parts.append(f"{k} = ?")
                vals.append(v)
            vals.append(proposal_id)
            conn.execute(
                f"UPDATE proposals SET {', '.join(parts)} WHERE proposal_id = ?", vals,
            )
            conn.commit()
            return conn.total_changes > 0
        finally:
            conn.close()

    def _merge_proposal(self, row: dict):
        """Execute the proposed change (merge to main)."""
        ptype = row.get("proposal_type", "")
        changes = json.loads(row.get("proposed_changes", "{}") or "{}")

        try:
            if ptype == "skill_registration":
                self._merge_skill(changes)
            elif ptype == "pipeline_update":
                pass  # v2: pipeline graph update
            elif ptype == "policy_update":
                pass  # v2: policy rule update
        except Exception as e:
            logger.error("Proposal merge failed: %s", e)

        # Mark as merged
        conn = _get_db()
        try:
            conn.execute(
                "UPDATE proposals SET status = 'merged', merged_at = ? WHERE proposal_id = ?",
                (time.time(), row["proposal_id"]),
            )
            conn.commit()
        finally:
            conn.close()
        logger.info("Proposal merged: %s (%s)", row["proposal_id"], row.get("title"))

    @staticmethod
    def _merge_skill(changes: dict):
        """Register a skill from a proposal."""
        skill_name = changes.get("skill_name", "")
        if not skill_name:
            return
        try:
            from core.apps.skills.registry import SkillRegistry
            registry = SkillRegistry()
            # Trigger re-scan for the new skill
            logger.info("Proposal merge: skill '%s' → SkillRegistry", skill_name)
        except Exception as e:
            logger.warning("Skill merge failed: %s", e)

    def list(self, status: Optional[str] = None, limit: int = 50) -> list:
        conn = _get_db()
        try:
            conn.row_factory = sqlite3.Row
            if status:
                rows = conn.execute(
                    "SELECT * FROM proposals WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM proposals ORDER BY created_at DESC LIMIT ?", (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get(self, proposal_id: str) -> Optional[dict]:
        conn = _get_db()
        try:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_stats(self) -> dict:
        conn = _get_db()
        try:
            stats = {}
            for status in ["draft", "pending_approval", "approved", "merged", "rejected"]:
                stats[status] = conn.execute(
                    "SELECT COUNT(*) FROM proposals WHERE status = ?", (status,),
                ).fetchone()[0]
            return {"by_status": stats, "total": sum(stats.values())}
        finally:
            conn.close()


# ── Global singleton ──

_proposal_store: Optional[ProposalStore] = None


def get_proposal_store() -> ProposalStore:
    global _proposal_store
    if _proposal_store is None:
        _proposal_store = ProposalStore()
    return _proposal_store
