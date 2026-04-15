"""
Human-in-the-Loop Approval System

Provides approval mechanisms for Agent decision loops.
Based on framework/patterns.md §7 Human-in-the-Loop 模式.

Approval rules:
- AMOUNT_THRESHOLD: Amount exceeds threshold
- SENSITIVE_OPERATION: Sensitive data/permission operations
- BATCH_OPERATION: Batch delete/modify operations
- FIRST_TIME: First time executing an operation type
"""

from .types import (
    RuleType,
    RequestStatus,
    ApprovalRule,
    ApprovalRequest,
    ApprovalResult,
    ApprovalContext,
)
from .manager import (
    ApprovalManager,
    create_approval_manager,
)

__all__ = [
    # Rule Types
    "RuleType",
    "RequestStatus",
    # Data Classes
    "ApprovalRule",
    "ApprovalRequest",
    "ApprovalResult",
    "ApprovalContext",
    # Manager
    "ApprovalManager",
    "create_approval_manager",
]