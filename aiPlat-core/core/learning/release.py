"""
Phase 6.6: Release candidate (offline, controlled publish/rollback).

This module only manages *learning artifacts* statuses. It does not apply changes
to runtime behaviors by itself.

Typical workflow:
1) Create RELEASE_CANDIDATE artifact that references a set of artifact_ids
2) (Optional) Require approval to publish
3) Publish: set candidate + referenced artifacts to PUBLISHED
4) Rollback: set candidate + referenced artifacts to ROLLED_BACK
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.harness.infrastructure.approval.manager import ApprovalManager
from core.harness.infrastructure.approval.types import ApprovalContext, ApprovalRule, RuleType, RequestStatus

from .types import LearningArtifact, LearningArtifactKind, LearningArtifactStatus


@dataclass
class ReleasePublishResult:
    status: str  # published|approval_required|not_found|not_approved|error
    approval_request_id: Optional[str] = None
    error: Optional[str] = None


def build_release_candidate(
    *,
    target_type: str,
    target_id: str,
    version: str,
    artifact_ids: List[str],
    summary: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    trace_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> LearningArtifact:
    return LearningArtifact(
        artifact_id=str(uuid.uuid4()),
        kind=LearningArtifactKind.RELEASE_CANDIDATE,
        target_type=target_type,
        target_id=target_id,
        version=version,
        status=LearningArtifactStatus.DRAFT,
        trace_id=trace_id,
        run_id=run_id,
        payload={"artifact_ids": artifact_ids, "summary": summary},
        metadata=metadata or {},
    )


def get_release_publish_rule() -> ApprovalRule:
    """A built-in rule used when enforcing approval for publishing releases."""
    return ApprovalRule(
        rule_id="learning_publish_release",
        rule_type=RuleType.SENSITIVE_OPERATION,
        name="学习产物发布审批",
        description="发布 learning release candidate 需要审批",
        priority=1,
        metadata={"sensitive_operations": ["learning:publish_release"]},
    )


def get_release_rollback_rule() -> ApprovalRule:
    """A built-in rule used when enforcing approval for rolling back releases."""
    return ApprovalRule(
        rule_id="learning_rollback_release",
        rule_type=RuleType.SENSITIVE_OPERATION,
        name="学习产物回滚审批",
        description="回滚 learning release candidate 需要审批",
        priority=1,
        metadata={"sensitive_operations": ["learning:rollback_release"]},
    )


async def require_publish_approval(
    *,
    approval_manager: ApprovalManager,
    user_id: str,
    candidate_id: str,
    details: str = "",
) -> str:
    rule = get_release_publish_rule()
    approval_manager.register_rule(rule)
    ctx = ApprovalContext(
        user_id=user_id,
        operation="learning:publish_release",
        operation_context={"details": details or f"publish release candidate: {candidate_id}"},
        metadata={"candidate_id": candidate_id},
    )
    req = approval_manager.create_request(ctx, rule=rule)
    # Ensure persistence in short-lived offline processes (CLI).
    try:
        await approval_manager._persist(req)  # type: ignore[attr-defined]
    except Exception:
        pass
    return req.request_id


async def require_rollback_approval(
    *,
    approval_manager: ApprovalManager,
    user_id: str,
    candidate_id: str,
    regression_report_id: Optional[str] = None,
    details: str = "",
) -> str:
    rule = get_release_rollback_rule()
    approval_manager.register_rule(rule)
    ctx = ApprovalContext(
        user_id=user_id,
        operation="learning:rollback_release",
        operation_context={"details": details or f"rollback release candidate: {candidate_id}"},
        metadata={"candidate_id": candidate_id, "regression_report_id": regression_report_id},
    )
    req = approval_manager.create_request(ctx, rule=rule)
    try:
        await approval_manager._persist(req)  # type: ignore[attr-defined]
    except Exception:
        pass
    return req.request_id


def is_approved(approval_manager: ApprovalManager, approval_request_id: str) -> bool:
    req = approval_manager.get_request(approval_request_id)
    if not req:
        return False
    return req.status in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED)
