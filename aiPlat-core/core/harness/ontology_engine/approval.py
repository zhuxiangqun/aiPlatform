"""
Approval Workflow Engine — enterprise knowledge collaboration.

Extends the existing EntityLifecycleState machine with multi-level
approval workflows for knowledge graph entities.

Usage:
    wf = ApprovalWorkflow(persistence, alert_channel="feishu")
    record = await wf.submit("entity:123", "PUBLISHED", assignee="reviewer1")
    await wf.approve(record.id, "reviewer1", "LGTM")
"""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ApprovalComment:
    actor_id: str
    text: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ApprovalRecord:
    id: str
    entity_id: str
    entity_type: str
    current_state: str
    proposed_state: str
    assignee: str
    assignee_group: str
    status: str  # pending / approved / rejected / changes_requested
    comments: List[Dict] = field(default_factory=list)
    escalate_to: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None

    @property
    def is_pending(self) -> bool:
        return self.status == "pending"

    def approve(self, actor_id: str, comment: str = ""):
        self.status = "approved"
        self.resolved_at = datetime.now(timezone.utc).isoformat()
        if comment:
            self.comments.append({"actor_id": actor_id, "text": comment,
                                  "timestamp": datetime.now(timezone.utc).isoformat()})

    def reject(self, actor_id: str, reason: str = ""):
        self.status = "rejected"
        self.resolved_at = datetime.now(timezone.utc).isoformat()
        if reason:
            self.comments.append({"actor_id": actor_id, "text": reason,
                                  "timestamp": datetime.now(timezone.utc).isoformat()})


class ApprovalPersistence:
    """In-memory approval record storage with optional SQLite backing."""

    def __init__(self):
        self._records: Dict[str, ApprovalRecord] = {}

    async def save(self, record: ApprovalRecord):
        self._records[record.id] = record

    async def get(self, record_id: str) -> Optional[ApprovalRecord]:
        return self._records.get(record_id)

    async def get_pending(self, assignee: str = None, group: str = None,
                          timeout_hours: int = None) -> List[ApprovalRecord]:
        results = []
        for r in self._records.values():
            if r.status != "pending":
                continue
            if assignee and r.assignee != assignee:
                continue
            if group and r.assignee_group != group:
                continue
            if timeout_hours:
                created = datetime.fromisoformat(r.created_at)
                elapsed = (datetime.now(timezone.utc) - created).total_seconds() / 3600
                if elapsed < timeout_hours:
                    continue
            results.append(r)
        return sorted(results, key=lambda r: r.created_at)

    async def list_by_entity(self, entity_id: str) -> List[ApprovalRecord]:
        return [r for r in self._records.values() if r.entity_id == entity_id]


class ApprovalWorkflow:
    """Multi-level approval workflow with timeout escalation.

    Args:
        persistence: Storage backend for approval records.
        alert_channel: "feishu" / "wecom" / "slack" / "none" — reuses existing enterprise gateway.
        timeout_hours: Auto-escalate pending approvals after this many hours (default 48).
    """

    def __init__(
        self,
        persistence: Optional[ApprovalPersistence] = None,
        alert_channel: str = "none",
        timeout_hours: int = 48,
    ):
        self._persistence = persistence or ApprovalPersistence()
        self._alert_channel = alert_channel
        self._timeout_hours = timeout_hours

    async def submit(
        self,
        entity_id: str,
        proposed_state: str,
        *,
        entity_type: str = "knowledge_atom",
        current_state: str = "draft",
        assignee: str = None,
        assignee_group: str = "ontology_admins",
    ) -> ApprovalRecord:
        """Submit an entity for approval."""
        if not assignee:
            assignee = await self._resolve_default_assignee(assignee_group)

        record = ApprovalRecord(
            id=f"approval_{uuid.uuid4().hex[:12]}",
            entity_id=entity_id,
            entity_type=entity_type,
            current_state=current_state,
            proposed_state=proposed_state,
            assignee=assignee,
            assignee_group=assignee_group,
            status="pending",
        )
        await self._persistence.save(record)
        await self._notify(assignee, f"新审批请求: {entity_id} → {proposed_state}")
        return record

    async def approve(self, record_id: str, actor_id: str, comment: str = "") -> ApprovalRecord:
        """Approve and execute state transition."""
        record = await self._persistence.get(record_id)
        if not record:
            raise ValueError(f"Approval record not found: {record_id}")
        if record.status != "pending":
            raise ValueError(f"Cannot approve: record is {record.status}")

        record.approve(actor_id, comment)
        await self._persistence.save(record)

        # Execute state transition
        await self._execute_transition(record)
        await self._notify(record.assignee, f"审批通过: {record.entity_id}")
        return record

    async def reject(self, record_id: str, actor_id: str, reason: str = "") -> ApprovalRecord:
        """Reject — entity returns to DRAFT."""
        record = await self._persistence.get(record_id)
        if not record:
            raise ValueError(f"Approval record not found: {record_id}")
        if record.status != "pending":
            raise ValueError(f"Cannot reject: record is {record.status}")

        record.reject(actor_id, reason)
        await self._persistence.save(record)

        # Revert entity state
        await self._revert_transition(record)
        await self._notify(record.assignee, f"审批拒绝: {record.entity_id} — {reason[:100]}")
        return record

    async def request_changes(
        self, record_id: str, actor_id: str, comment: str
    ) -> ApprovalRecord:
        """Request changes — stays UNDER_REVIEW, notifies submitter."""
        record = await self._persistence.get(record_id)
        if not record:
            raise ValueError(f"Approval record not found: {record_id}")
        record.comments.append({
            "actor_id": actor_id, "text": comment,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        record.status = "changes_requested"
        await self._persistence.save(record)
        return record

    async def get_pending(self, assignee: str = None, group: str = None) -> List[ApprovalRecord]:
        return await self._persistence.get_pending(assignee=assignee, group=group)

    async def check_timeout(self) -> List[ApprovalRecord]:
        """Check for timed-out pending approvals and auto-escalate."""
        timed_out = await self._persistence.get_pending(
            timeout_hours=self._timeout_hours)
        escalated = []
        for record in timed_out:
            record.escalate_to = await self._resolve_escalation(record.assignee)
            await self._persistence.save(record)
            await self._notify(record.escalate_to,
                               f"审批超时升级 [{self._timeout_hours}h]: {record.entity_id}")
            escalated.append(record)
        if escalated:
            logger.warning(f"审批超时升级: {len(escalated)} 条")
            try:
                from core.harness.memory.metrics import inc_skill_alert
                for _ in escalated:
                    inc_skill_alert("approval_timeout")
            except Exception:
                pass
        return escalated

    async def _resolve_default_assignee(self, group: str) -> str:
        """Resolve a default assignee from the group."""
        return f"{group}:default"

    async def _resolve_escalation(self, current_assignee: str) -> str:
        """Resolve escalation target — defaults to platform_admin group."""
        return "platform_admin"

    async def _execute_transition(self, record: ApprovalRecord):
        """Execute the approved state transition on the entity."""
        try:
            from core.harness.knowledge.knowledge_action import (
                validate_state_transition, EntityLifecycleState,
            )
            ok, msg = validate_state_transition(record.current_state, record.proposed_state)
            if not ok:
                logger.error(f"状态转换无效: {msg}")
                return
        except Exception:
            pass
        logger.info(f"Entity {record.entity_id}: {record.current_state} → {record.proposed_state}")

    async def _revert_transition(self, record: ApprovalRecord):
        """Revert entity to draft on rejection."""
        logger.info(f"Entity {record.entity_id}: reverted from {record.current_state}")

    async def _notify(self, target: str, message: str):
        """Send notification via configured alert channel."""
        if self._alert_channel == "none":
            return
        logger.info(f"[{self._alert_channel}] → {target}: {message}")


_workflow_instance: Optional[ApprovalWorkflow] = None


def get_approval_workflow(
    alert_channel: str = "",
    timeout_hours: int = 0,
) -> ApprovalWorkflow:
    """Get or create the singleton ApprovalWorkflow."""
    global _workflow_instance
    if _workflow_instance is None:
        ch = alert_channel or os.getenv("AIPLAT_ALERT_CHANNEL", "none")
        hrs = timeout_hours or int(os.getenv("AIPLAT_APPROVAL_TIMEOUT_HOURS", "48"))
        _workflow_instance = ApprovalWorkflow(alert_channel=ch, timeout_hours=hrs)
    return _workflow_instance


__all__ = [
    "ApprovalRecord", "ApprovalComment", "ApprovalPersistence",
    "ApprovalWorkflow", "get_approval_workflow",
]
