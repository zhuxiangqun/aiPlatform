"""
Async action store — aiosqlite-backed audit + pending-approval persistence.

Tables:
  - action_audit: immutable execution records with entity snapshots
  - pending_approvals: persistent stake locks for approval workflows
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Literal

logger = logging.getLogger(__name__)


class ActionStore:
    """Async persistence for action audit trail and pending approvals."""

    def __init__(self, db_path: str = "./data/execution_store.db"):
        self.db_path = db_path

    async def initialize(self) -> None:
        """Create tables (idempotent)."""
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS action_audit (
                    audit_id TEXT PRIMARY KEY,
                    action_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    domain_id TEXT NOT NULL,
                    from_state TEXT,
                    to_state TEXT,
                    actor TEXT,
                    role TEXT,
                    params TEXT,
                    result_status TEXT,
                    constraint_type TEXT,
                    effect_summary TEXT,
                    compensation TEXT,
                    entity_snapshot TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS pending_approvals (
                    lock_id TEXT PRIMARY KEY,
                    action_id TEXT NOT NULL,
                    entity_ref TEXT NOT NULL,
                    params TEXT,
                    actor TEXT,
                    status TEXT DEFAULT 'pending',
                    locked_until TEXT,
                    resolved_at TEXT,
                    resolver TEXT,
                    resolve_reason TEXT,
                    requested_at TEXT DEFAULT (datetime('now'))
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_entity ON action_audit(entity_id, domain_id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_action ON action_audit(action_id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_approvals(status)"
            )
            # Phase 3: ontology proposals table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ontology_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    domain_id TEXT NOT NULL,
                    version_from TEXT,
                    version_to TEXT,
                    changes TEXT,
                    status TEXT DEFAULT 'draft',
                    author TEXT,
                    impact_analysis TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            await db.commit()

    # ═══════════════════════════════════════════════════════
    # Audit
    # ═══════════════════════════════════════════════════════

    async def insert_audit(self, record: Dict[str, Any]) -> str:
        """Write an audit entry. Returns audit_id."""
        import aiosqlite
        audit_id = record.get("audit_id") or f"aud_{uuid.uuid4().hex[:16]}"
        snapshot = record.get("entity_snapshot")
        snapshot_json = json.dumps(snapshot, ensure_ascii=False) if snapshot else None

        # Auto-tag: if result is not_found and both states empty, flag it
        effect = record.get("effect_summary", "")
        if record.get("result_status") == "not_found" and not effect.strip():
            effect = "[ENTITY_MISSING]"

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO action_audit (
                    audit_id, action_id, entity_id, domain_id,
                    from_state, to_state, actor, role, params,
                    result_status, constraint_type, effect_summary,
                    compensation, entity_snapshot
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                audit_id,
                record.get("action_id", ""),
                record.get("entity_id", ""),
                record.get("domain_id", ""),
                record.get("from_state", ""),
                record.get("to_state", ""),
                record.get("actor", "system"),
                record.get("role", ""),
                json.dumps(record.get("params", {}), ensure_ascii=False),
                record.get("result_status", "executed"),
                record.get("constraint_type", ""),
                effect,
                record.get("compensation", ""),
                snapshot_json,
            ))
            await db.commit()
        return audit_id

    async def list_audit(self, entity_id: str = "", domain_id: str = "",
                         limit: int = 50) -> List[Dict[str, Any]]:
        """Query audit entries by entity/domain."""
        import aiosqlite
        results: List[Dict[str, Any]] = []
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if entity_id and domain_id:
                async with db.execute(
                    "SELECT * FROM action_audit WHERE entity_id=? AND domain_id=? ORDER BY created_at DESC LIMIT ?",
                    (entity_id, domain_id, limit),
                ) as cur:
                    results = [dict(r) for r in await cur.fetchall()]
            elif entity_id:
                async with db.execute(
                    "SELECT * FROM action_audit WHERE entity_id=? ORDER BY created_at DESC LIMIT ?",
                    (entity_id, limit),
                ) as cur:
                    results = [dict(r) for r in await cur.fetchall()]
            else:
                async with db.execute(
                    "SELECT * FROM action_audit ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ) as cur:
                    results = [dict(r) for r in await cur.fetchall()]
        return results

    # ═══════════════════════════════════════════════════════
    # Pending Approvals
    # ═══════════════════════════════════════════════════════

    async def insert_pending(self, approval: Dict[str, Any]) -> str:
        """Create a pending-approval record. Returns lock_id."""
        import aiosqlite
        lock_id = approval.get("lock_id") or f"stake_{uuid.uuid4().hex[:16]}"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO pending_approvals (
                    lock_id, action_id, entity_ref, params, actor, locked_until, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                lock_id,
                approval.get("action_id", ""),
                approval.get("entity_ref", ""),
                json.dumps(approval.get("params", {}), ensure_ascii=False),
                approval.get("actor", "system"),
                approval.get("locked_until"),
                "pending",
            ))
            await db.commit()
        return lock_id

    async def get_pending(self, lock_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a pending approval by lock_id."""
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM pending_approvals WHERE lock_id = ?", (lock_id,)
            ) as cur:
                row = await cur.fetchone()
                if not row:
                    return None
                d = dict(row)
                if d.get("params"):
                    try:
                        d["params"] = json.loads(d["params"])
                    except (json.JSONDecodeError, TypeError):
                        pass  # noqa: cleanup-best-effort — params may be malformed JSON
                return d

    async def resolve_pending(
        self,
        lock_id: str,
        status: Literal["approved", "rejected", "expired"],
        resolver: str = "system",
        reason: str = "",
    ) -> bool:
        """Mark a pending approval as resolved. Returns True if updated."""
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """UPDATE pending_approvals
                   SET status=?, resolved_at=datetime('now'), resolver=?, resolve_reason=?
                   WHERE lock_id=? AND status='pending'""",
                (status, resolver, reason, lock_id),
            )
            await db.commit()
            return cur.rowcount > 0

    async def list_pending_by_entity(self, entity_ref: str) -> List[Dict[str, Any]]:
        """List all pending approvals for an entity."""
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM pending_approvals WHERE entity_ref=? AND status='pending' ORDER BY requested_at DESC",
                (entity_ref,),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def expire_stale_approvals(self, now_ts: Optional[float] = None) -> int:
        """Auto-expire approvals past their locked_until timestamp. Returns count."""
        import aiosqlite
        ts = now_ts or time.time()
        deadline = datetime.fromtimestamp(ts).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """UPDATE pending_approvals
                   SET status='expired', resolved_at=datetime('now'), resolve_reason='auto-expired'
                   WHERE status='pending' AND locked_until IS NOT NULL AND locked_until < ?""",
                (deadline,),
            )
            await db.commit()
            return cur.rowcount

    # ═══════════════════════════════════════════════════════
    # Ontology proposals (Phase 3)
    # ═══════════════════════════════════════════════════════

    async def insert_ontology_proposal(
        self, proposal_id: str, domain_id: str, version_from: str, version_to: str,
        changes: str, status: str, author: str, impact: str,
    ) -> str:
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ontology_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    domain_id TEXT NOT NULL,
                    version_from TEXT,
                    version_to TEXT,
                    changes TEXT,
                    status TEXT DEFAULT 'draft',
                    author TEXT,
                    impact_analysis TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            await db.execute("""
                INSERT INTO ontology_proposals
                (proposal_id, domain_id, version_from, version_to, changes, status, author, impact_analysis)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (proposal_id, domain_id, version_from, version_to, changes, status, author, impact))
            await db.commit()
        return proposal_id

    async def get_ontology_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM ontology_proposals WHERE proposal_id = ?", (proposal_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def update_ontology_proposal_status(self, proposal_id: str, status: str) -> bool:
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "UPDATE ontology_proposals SET status = ? WHERE proposal_id = ?",
                (status, proposal_id),
            )
            await db.commit()
            return cur.rowcount > 0

    async def list_ontology_proposals(self, domain_id: str) -> List[Dict[str, Any]]:
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM ontology_proposals WHERE domain_id = ? ORDER BY created_at DESC LIMIT 50",
                (domain_id,),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
