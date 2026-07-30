"""
Decision Throttle (v3.1, 2026-07-30) — Palantir MSS-aligned rate governance.

Prevents "rubber-stamp" effect when AI generates decisions faster than
humans can meaningfully review. Checks action_audit table for execution
velocity and blocks/warns when limits are exceeded.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from core.harness.infrastructure.action_store import ActionStore

logger = logging.getLogger(__name__)


class DecisionThrottle:
    """Real-time rate limiter based on audit trail velocity."""

    def __init__(self, store: Optional[ActionStore] = None):
        self.store = store or ActionStore()

    async def check_rate_limit(
        self,
        actor: str,
        action_id: str,
        domain_id: str,
        time_window_sec: int = 3600,
        limit: int = 100,
        block_on_breach: bool = True,
    ) -> Dict[str, Any]:
        """Check if actor has exceeded the execution rate for an action.

        Returns:
            allowed: bool
            count: current executions in window
            limit: configured limit
            reason: str (if blocked)
            require_justification: bool
        """
        if not actor or actor == "system":
            return {"allowed": True, "count": 0, "limit": limit}

        import aiosqlite

        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=time_window_sec)).isoformat()
        async with aiosqlite.connect(self.store.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT COUNT(*) as cnt FROM action_audit
                   WHERE actor=? AND action_id=? AND domain_id=?
                   AND result_status IN ('executed','log_only')
                   AND created_at > ?""",
                (actor, action_id, domain_id, cutoff),
            ) as cur:
                row = await cur.fetchone()
                count = row["cnt"] if row else 0

        if count >= limit:
            reason = (
                f"Rate limit: {actor} executed '{action_id}' {count}× "
                f"in {time_window_sec // 60}min (limit={limit})"
            )
            if block_on_breach:
                logger.warning("THROTTLE BLOCK: %s", reason)
                return {
                    "allowed": False, "count": count, "limit": limit,
                    "window_seconds": time_window_sec, "reason": reason,
                    "require_justification": True,
                }
            else:
                logger.warning("THROTTLE WARN: %s", reason)

        return {
            "allowed": True, "count": count, "limit": limit,
            "window_seconds": time_window_sec, "reason": None,
            "require_justification": False,
        }

    async def record_justification(
        self, actor: str, action_id: str, entity_id: str, justification: str,
    ) -> None:
        """Log a human override justification (stored in action_audit params)."""
        logger.info("Justification: %s/%s by %s — %s",
                     action_id, entity_id, actor, justification[:200])
